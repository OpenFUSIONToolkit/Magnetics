"""MODESPEC-style rotating-mode spectral analysis.

Translated from OMFIT's spectrogram_prep.py and spectrogram_useful_stuff.py.
Pure functions over numpy arrays — no device-specific data access, no GUI concerns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.fft import next_fast_len, rfft, rfftfreq
from scipy.integrate import cumulative_trapezoid
from scipy.ndimage import uniform_filter1d
from scipy.signal import coherence as scipy_coherence
from scipy.signal import csd, get_window, resample


@dataclass(slots=True)
class CrossSpectrumResult:
    kind: str
    frequency: NDArray[np.floating]
    power: NDArray[np.floating]
    coherence: NDArray[np.floating]
    phase: NDArray[np.floating]
    phase_error: NDArray[np.floating] | None = None     # 1σ phase (deg) per freq
    amplitude_error: NDArray[np.floating] | None = None  # 1σ |Gxy| per freq
    n_segments: int | None = None                        # Welch averages K
    mode_number: NDArray[np.integer] | None = None
    rms_by_mode: NDArray[np.floating] | None = None
    mode_indices: NDArray[np.integer] | None = None


@dataclass(slots=True)
class SpectrogramResult:
    kind: str
    time: NDArray[np.floating]
    frequency: NDArray[np.floating]
    power: NDArray[np.floating]
    coherence: NDArray[np.floating]
    mode_number: NDArray[np.integer]
    rms_by_mode: NDArray[np.floating]
    mode_indices: NDArray[np.integer]


@dataclass(slots=True)
class ModeAtFrequencyResult:
    kind: str
    frequency: float
    phase: NDArray[np.floating]
    amplitude: NDArray[np.floating]
    coherence: NDArray[np.floating]
    toroidal_angle: NDArray[np.floating]
    poloidal_angle: NDArray[np.floating] | None = None
    phase_error: NDArray[np.floating] | None = None      # 1σ phase (deg) per probe
    amplitude_error: NDArray[np.floating] | None = None  # 1σ amplitude per probe


@dataclass(slots=True)
class ToroidalFitResult:
    kind: str
    n: int                      # best-fit toroidal mode number
    intercept_deg: float        # fitted phase at phi = 0 (deg), in [0, 360)
    resultant: float            # clustering quality in [0, 1] (1 = perfect fit)
    frequency: float            # Hz, the frequency the fit was evaluated at
    toroidal_angle: NDArray[np.floating]   # measured probe angles (deg)
    phase: NDArray[np.floating]            # measured phases (deg), wrapped [0, 360)
    phase_sigma: float | None = None       # 1σ of the fitted intercept (deg)
    n_confidence: float | None = None      # posterior prob. of the best n in [0, 1]


# ---------------------------------------------------------------------------
# Signal conditioning
# ---------------------------------------------------------------------------


def downsample(
    time: NDArray[np.floating],
    signal: NDArray[np.floating],
    *,
    t_range: tuple[float, float] | None = None,
    sample_rate: float = 2e5,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Trim a signal to a time range and resample to a uniform rate.

    Inputs:
        time (ndarray): sample times (s).
        signal (ndarray): signal samples.
        t_range (tuple[float, float] | None): (start, stop) in s; None keeps all.
        sample_rate (float): target rate (Hz).
    Returns:
        time_new (ndarray): resampled sample times (s).
        signal_new (ndarray): resampled signal.
    """
    if t_range is not None:
        mask = (time >= t_range[0]) & (time <= t_range[1])
        time = time[mask]
        signal = signal[mask]

    n_samples = int((time[-1] - time[0]) * sample_rate)
    signal_new, time_new = resample(signal, n_samples, t=time)
    return time_new, signal_new


def integrate_bdot(
    time: NDArray[np.floating],
    signal: NDArray[np.floating],
    *,
    highpass_window: float | None = None,
) -> NDArray[np.floating]:
    """Integrate dB/dt → B. High-pass filters first to suppress integrator drift:
    mean subtraction, or running-average subtraction when highpass_window is given.

    Inputs:
        time (ndarray): sample times (s).
        signal (ndarray): dB/dt samples.
        highpass_window (float | None): running-average window (s); None subtracts the mean.
    Returns:
        B (ndarray): the integrated signal.
    """
    dt = (time[-1] - time[0]) / (len(time) - 1)

    if highpass_window is None:
        filtered = signal - np.mean(signal)
    else:
        n_pts = int(np.round(highpass_window / dt / 2.0) * 2 + 1)
        if n_pts > 1:
            filtered = signal - uniform_filter1d(signal, size=n_pts)
        else:
            filtered = signal - np.mean(signal)

    return cumulative_trapezoid(filtered, time, initial=0)


# ---------------------------------------------------------------------------
# Core 2-point spectral analysis
# ---------------------------------------------------------------------------


def _welch_segments(n_samples: int, nperseg: int | None) -> int:
    """Number of 50%-overlap Welch segments scipy averages over — the K in the
    cross-spectral random-error formulas. Mirrors scipy's defaults (nperseg→256
    capped at the record, noverlap = nperseg // 2)."""
    nps = nperseg if nperseg is not None else min(256, n_samples)
    nps = max(1, min(nps, n_samples))
    step = max(1, nps - nps // 2)
    return max(1, 1 + (n_samples - nps) // step)


def _cross_spectral_errors(
    coherence: NDArray[np.floating],
    power: NDArray[np.floating],
    n_segments: int,
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """1σ random errors of cross-phase (deg) and cross-amplitude from K averages
    (Bendat & Piersol): σ_φ = √(1−γ²)/(γ√(2K)) rad, σ_|G| = |G|/(γ√K), with γ the
    magnitude coherence. Incoherent bins (γ→0) are capped at ±180° rather than ∞."""
    gamma = np.sqrt(np.clip(coherence, 0.0, 1.0))
    g = np.clip(gamma, 1e-3, 1.0)
    k = max(1, int(n_segments))
    phase_err = np.rad2deg(np.sqrt(np.clip(1.0 - g**2, 0.0, 1.0)) / (g * np.sqrt(2.0 * k)))
    phase_err = np.minimum(phase_err, 180.0)
    amp_err = power / (g * np.sqrt(k))
    return phase_err, amp_err


def cross_spectrum(
    sig1: NDArray[np.floating],
    sig2: NDArray[np.floating],
    sample_rate: float,
    *,
    delta_phi: float | None = None,
    nperseg: int | None = None,
) -> CrossSpectrumResult:
    """2-point cross-power spectral density, coherence, and phase between two probes.
    With delta_phi, also returns mode number n = round(phase / delta_phi) and per-mode RMS.

    Inputs:
        sig1 (ndarray): first probe time series.
        sig2 (ndarray): second probe time series.
        sample_rate (float): sampling rate (Hz).
        delta_phi (float | None): toroidal separation (deg); enables mode-number output.
        nperseg (int | None): Welch segment length for csd/coherence; None uses scipy's
            default (256). Set below the signal length on short slices to keep multiple
            averaging segments — coherence is meaningless from a single segment.
    Returns:
        result (CrossSpectrumResult): frequency/power/coherence/phase, plus
            mode_number/rms_by_mode/mode_indices set iff delta_phi is given.
    """
    f, pxy = csd(sig2, sig1, fs=sample_rate, nperseg=nperseg)
    _, coh = scipy_coherence(sig2, sig1, fs=sample_rate, nperseg=nperseg)

    power = np.abs(pxy)
    phase = np.rad2deg(np.angle(pxy))

    k = _welch_segments(int(min(np.size(sig1), np.size(sig2))), nperseg)
    phase_error, amplitude_error = _cross_spectral_errors(coh, power, k)

    if delta_phi is None:
        return CrossSpectrumResult(
            kind="cross_spectrum",
            frequency=f,
            power=power,
            coherence=coh,
            phase=phase,
            phase_error=phase_error,
            amplitude_error=amplitude_error,
            n_segments=k,
        )

    if delta_phi == 0:
        raise ValueError("delta_phi must be non-zero to compute mode numbers")

    mode = np.rint(phase / delta_phi).astype(np.intp)

    n_modes = int(np.ceil(180.0 / abs(delta_phi) - 0.5) * 2)
    n_lo = -(n_modes // 2)
    n_hi = n_modes // 2
    mode_indices = np.arange(n_lo, n_hi + 1, dtype=np.intp)

    df = f[1] - f[0]
    rms = np.array(
        [np.sqrt(np.sum(power[mode == m]) * df) for m in mode_indices]
    )

    return CrossSpectrumResult(
        kind="cross_spectrum",
        frequency=f,
        power=power,
        coherence=coh,
        phase=phase,
        phase_error=phase_error,
        amplitude_error=amplitude_error,
        n_segments=k,
        mode_number=mode,
        rms_by_mode=rms,
        mode_indices=mode_indices,
    )


# ---------------------------------------------------------------------------
# Short-time FFT engine
# ---------------------------------------------------------------------------


def _stft(
    signal: NDArray[np.floating],
    n_fft: int,
    hop: int,
    window: NDArray[np.floating],
    *,
    detrend: bool = True,
) -> tuple[NDArray[np.complexfloating], NDArray[np.intp]]:
    """Batched single-pass short-time FFT.

    Frames the signal at the given hop, applies the window, and rffts every frame in
    one vectorized call — no per-window Python loop, no per-window FFT planning.

    Inputs:
        signal (ndarray): 1-D real signal (single precision recommended).
        n_fft (int): window length (samples).
        hop (int): stride between window starts (samples).
        window (ndarray): taper of length n_fft.
        detrend (bool): subtract each window's mean before the FFT, suppressing the
            DC / slow-drift band (matches scipy.signal.csd's detrend='constant').
    Returns:
        spec (ndarray): complex STFT, shape (n_frames, n_fft // 2 + 1).
        starts (ndarray): frame start indices into signal.
    """
    n = signal.size
    if n < n_fft:
        frame = np.zeros((1, n_fft), dtype=signal.dtype)
        frame[0, :n] = signal
        if detrend:
            frame[0, :n] -= frame[0, :n].mean()
        return rfft(frame * window, axis=1), np.array([0], dtype=np.intp)

    starts = np.arange(0, n - n_fft + 1, hop, dtype=np.intp)
    idx = starts[:, None] + np.arange(n_fft)[None, :]
    frames = signal[idx]
    if detrend:
        frames = frames - frames.mean(axis=1, keepdims=True)
    frames = frames * window[None, :]
    return rfft(frames, axis=1), starts


# ---------------------------------------------------------------------------
# Spectrogram
# ---------------------------------------------------------------------------


def stft_layout(
    n_samples: int, sample_rate: float, slice_duration: float
) -> tuple[int, int, int]:
    """FFT length, native 50%-overlap hop, and natural column count for an STFT.

    Single source of truth for the sliding-window geometry, shared by
    ``compute_spectrogram`` and the streaming/contract layer so the two cannot drift.

    Inputs:
        n_samples (int): signal length (samples).
        sample_rate (float): sampling rate (Hz).
        slice_duration (float): FFT window width (s).
    Returns:
        (n_fft, natural_hop, n_cols_natural): window length, 50%-overlap stride, and
        the number of windows at that stride.
    """
    n_fft = max(8, int(next_fast_len(int(round(slice_duration * sample_rate)))))
    natural_hop = max(1, n_fft // 2)
    n_cols_natural = max(1, (n_samples - n_fft) // natural_hop + 1)
    return n_fft, natural_hop, n_cols_natural


def compute_spectrogram(
    time: NDArray[np.floating],
    sig1: NDArray[np.floating],
    sig2: NDArray[np.floating],
    delta_phi: float,
    *,
    slice_duration: float = 0.001,
    window: str = "hann",
    max_columns: int = 2000,
    coherence_smooth: int = 5,
) -> SpectrogramResult:
    """Cross-power spectrogram, coherence, and toroidal mode number vs (time, frequency).

    Engine: one batched, single-precision short-time FFT per probe (no per-window loop),
    with the column count decimated to ``max_columns`` so cost scales with the display,
    not the record length. Physics: cross-power = |conj(S1)·S2|, frequency-smoothed
    coherence, n = round(phase / delta_phi), and per-mode RMS — identical to the 2-point
    definitions in ``cross_spectrum``.

    Inputs:
        time (ndarray): sample times (s); assumed uniformly sampled.
        sig1 (ndarray): first probe time series.
        sig2 (ndarray): second probe time series.
        delta_phi (float): toroidal separation (deg); must be non-zero.
        slice_duration (float): FFT window width (s) — sets the frequency resolution.
        window (str): scipy window name for the taper.
        max_columns (int): cap on spectrogram time columns (decimation lever).
        coherence_smooth (int): frequency-bin width for the coherence estimate (>1).
    Returns:
        result (SpectrogramResult): power/coherence/mode_number as (n_times, n_freqs)
            arrays, with time/frequency/rms_by_mode/mode_indices.
    """
    if delta_phi == 0:
        raise ValueError("delta_phi must be non-zero to compute mode numbers")

    time = np.asarray(time)
    s1 = np.ascontiguousarray(sig1, dtype=np.float32)
    s2 = np.ascontiguousarray(sig2, dtype=np.float32)
    n = s1.size

    dt = float(np.median(np.diff(time)))
    sample_rate = 1.0 / dt

    n_fft, natural_hop, n_cols_natural = stft_layout(n, sample_rate, slice_duration)
    if n_cols_natural > max_columns:
        hop = max(natural_hop, (n - n_fft) // max(1, max_columns - 1))
    else:
        hop = natural_hop

    win = get_window(window, n_fft, fftbins=True).astype(np.float32)

    spec1, starts = _stft(s1, n_fft, hop, win)
    spec2, _ = _stft(s2, n_fft, hop, win)

    # Cross-power / phase (vectorized over every window at once). The conjugation
    # order matches cross_spectrum's scipy.signal.csd(sig2, sig1) convention so the
    # spectrogram and the single-window 2-point analysis report the same *signed* n.
    cross = np.conj(spec2) * spec1
    power = np.abs(cross)
    phase = np.rad2deg(np.angle(cross))

    # Coherence needs averaging; smooth the auto/cross spectra over frequency bins.
    if coherence_smooth > 1:
        sxx = uniform_filter1d(np.abs(spec1) ** 2, coherence_smooth, axis=1)
        syy = uniform_filter1d(np.abs(spec2) ** 2, coherence_smooth, axis=1)
        sxy = uniform_filter1d(cross.real, coherence_smooth, axis=1) + 1j * uniform_filter1d(
            cross.imag, coherence_smooth, axis=1
        )
        coh = (np.abs(sxy) ** 2) / (sxx * syy + 1e-30)
    else:
        coh = np.ones_like(power)

    mode = np.rint(phase / delta_phi).astype(np.intp)

    frequency = rfftfreq(n_fft, d=dt)
    t_centers = time[starts] + (n_fft / 2.0) * dt

    n_modes = int(np.ceil(180.0 / abs(delta_phi) - 0.5) * 2)
    mode_indices = np.arange(-(n_modes // 2), n_modes // 2 + 1, dtype=np.intp)

    df = frequency[1] - frequency[0]
    rms = np.empty((power.shape[0], mode_indices.size))
    for j, m in enumerate(mode_indices):
        rms[:, j] = np.sqrt(np.sum(power * (mode == m), axis=1) * df)

    return SpectrogramResult(
        kind="spectrogram",
        time=t_centers,
        frequency=frequency,
        power=power,
        coherence=coh,
        mode_number=mode,
        rms_by_mode=rms,
        mode_indices=mode_indices,
    )


# ---------------------------------------------------------------------------
# Spectrogram de-noising
# ---------------------------------------------------------------------------


def denoise_spectrogram(
    result: SpectrogramResult,
    *,
    coherence_min: float = 0.5,
    power_floor_k: float | None = 3.0,
    floor_percentile: float = 50.0,
) -> SpectrogramResult:
    """Suppress low-amplitude / incoherent cells by coherence gating and a per-frequency
    power floor; gated cells get power 0, and rms_by_mode is recomputed from what survives.

    Inputs:
        result (SpectrogramResult): spectrogram to clean.
        coherence_min (float): drop cells with coherence below this (0–1).
        power_floor_k (float | None): drop cells below k × per-frequency floor; None skips.
        floor_percentile (float): percentile over time defining the floor (50 = median).
    Returns:
        result (SpectrogramResult): copy with gated power zeroed and rms_by_mode recomputed.
    """
    keep = result.coherence >= coherence_min

    if power_floor_k is not None:
        floor = np.percentile(result.power, floor_percentile, axis=0)  # (n_freqs,)
        keep &= result.power >= power_floor_k * floor

    power = np.where(keep, result.power, 0.0)

    # Recompute per-mode RMS from the surviving power (gated cells contribute nothing).
    df = result.frequency[1] - result.frequency[0]
    rms = np.empty((power.shape[0], len(result.mode_indices)))
    for j, m in enumerate(result.mode_indices):
        rms[:, j] = np.sqrt(np.sum(power * (result.mode_number == m), axis=1) * df)

    return SpectrogramResult(
        kind="spectrogram",
        time=result.time,
        frequency=result.frequency,
        power=power,
        coherence=result.coherence,
        mode_number=result.mode_number,
        rms_by_mode=rms,
        mode_indices=result.mode_indices,
    )


# ---------------------------------------------------------------------------
# Batched full-array STFT (compute once, slice per cursor — eigspec speed path)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ArrayShapeSpectrum:
    kind: str
    time: NDArray[np.floating]              # (n_times,) window-center times (s)
    frequency: float                        # Hz, the analysis frequency (band center)
    freq_band: NDArray[np.floating]         # (n_band,) Hz kept around `frequency`
    spec: NDArray[np.complexfloating]       # (n_probes, n_times, n_band) complex STFT


def array_shape_spectrum(
    signals: NDArray[np.floating],
    time: NDArray[np.floating],
    frequency: float,
    *,
    slice_duration: float = 0.001,
    window: str = "hann",
    max_columns: int = 2000,
    n_band: int = 5,
) -> ArrayShapeSpectrum:
    """One batched short-time FFT per probe, keeping only a few frequency bins around
    ``frequency``. Computed once per shot; the cursor/track analyses then read the
    complex array pattern at any time by indexing this — no per-cursor cross-spectra.

    Inputs:
        signals (ndarray): probe time series, shape (n_probes, n_samples).
        time (ndarray): sample times (s), uniform.
        frequency (float): analysis frequency (Hz); the kept band is centered here.
        slice_duration (float): FFT window width (s).
        n_band (int): number of frequency bins kept around `frequency` (for the local
            coherence average in ``mode_from_spectrum``).
    Returns:
        result (ArrayShapeSpectrum): the per-probe complex STFT band + axes.
    """
    sig = np.ascontiguousarray(signals, dtype=np.float32)
    n_probes, n = sig.shape
    time = np.asarray(time)
    dt = float(np.median(np.diff(time)))

    n_fft, natural_hop, n_cols_natural = stft_layout(n, 1.0 / dt, slice_duration)
    hop = (natural_hop if n_cols_natural <= max_columns
           else max(natural_hop, (n - n_fft) // max(1, max_columns - 1)))
    win = get_window(window, n_fft, fftbins=True).astype(np.float32)

    freqs = rfftfreq(n_fft, d=dt)
    fi = int(np.argmin(np.abs(freqs - frequency)))
    lo = max(0, min(fi - n_band // 2, freqs.size - n_band))
    hi = lo + n_band

    bands = []
    starts = None
    for i in range(n_probes):
        s, starts = _stft(sig[i], n_fft, hop, win)     # (n_frames, n_freqs)
        bands.append(s[:, lo:hi].astype(np.complex64))
    spec = np.stack(bands, axis=0)                       # (n_probes, n_frames, n_band)
    t_centers = time[starts] + (n_fft / 2.0) * dt
    return ArrayShapeSpectrum(
        kind="array_shape_spectrum",
        time=t_centers, frequency=float(freqs[fi]),
        freq_band=freqs[lo:hi], spec=spec,
    )


def mode_from_spectrum(
    spectrum: ArrayShapeSpectrum,
    angle_deg: NDArray[np.floating],
    t0_s: float,
    *,
    ref: int = 0,
    t_smooth: int = 3,
) -> ModeAtFrequencyResult:
    """Per-probe phase/amplitude/coherence (+1σ) at one time, read from a precomputed
    ``ArrayShapeSpectrum`` — the fast equivalent of ``extract_mode_at_frequency``.

    The cross-spectrum of each probe vs. the reference is averaged over the kept
    frequency band and a few neighboring time columns (the Welch averaging that yields
    coherence and the Bendat–Piersol σ), then indexed by the column nearest ``t0_s``.
    """
    band = spectrum.spec                                 # (n_probes, n_times, n_band)
    ti = int(np.argmin(np.abs(spectrum.time - t0_s)))
    t_lo = max(0, min(ti - t_smooth // 2, band.shape[1] - t_smooth))
    cells = band[:, t_lo:t_lo + t_smooth, :]             # (n_probes, n_t, n_band)
    ref_cells = cells[ref]                               # (n_t, n_band)

    # conj(sig)·ref to match scipy.signal.csd(sig, ref)'s convention in
    # cross_spectrum, so the signed n agrees with extract_mode_at_frequency.
    cross = np.mean(np.conj(cells) * ref_cells[None], axis=(1, 2))   # (n_probes,)
    sxx = float(np.mean(np.abs(ref_cells) ** 2))
    syy = np.mean(np.abs(cells) ** 2, axis=(1, 2))                   # (n_probes,)

    power = np.abs(cross)
    phase = np.rad2deg(np.angle(cross))
    phase[phase < 0] += 360.0
    coherence = (np.abs(cross) ** 2) / (sxx * syy + 1e-30)

    k = max(1, cells.shape[1] * cells.shape[2])
    phase_err, amp_err = _cross_spectral_errors(coherence, power, k)
    phase_err[ref] = np.nan
    amp_err[ref] = np.nan

    return ModeAtFrequencyResult(
        kind="mode_at_frequency",
        frequency=spectrum.frequency,
        phase=phase, amplitude=power, coherence=coherence,
        toroidal_angle=np.asarray(angle_deg, dtype=np.float64),
        phase_error=phase_err, amplitude_error=amp_err,
    )


# ---------------------------------------------------------------------------
# Multi-probe mode extraction at a single frequency
# ---------------------------------------------------------------------------


def extract_mode_at_frequency(
    signals: NDArray[np.floating],
    toroidal_angles: NDArray[np.floating],
    time: NDArray[np.floating],
    *,
    sample_rate: float | None = None,
    frequency: float | None = None,
    t_range: tuple[float, float] | None = None,
    poloidal_angles: NDArray[np.floating] | None = None,
    nperseg: int | None = None,
) -> ModeAtFrequencyResult:
    """Phase, amplitude, and coherence at one frequency for each probe vs. the first,
    for phase-vs-angle mode fitting; frequency=None picks the reference's peak-power bin.

    Inputs:
        signals (ndarray): probe time series, shape (n_probes, n_samples).
        toroidal_angles (ndarray): probe toroidal angles (deg).
        time (ndarray): sample times (s).
        sample_rate (float | None): sampling rate (Hz); inferred from time if None.
        frequency (float | None): frequency to evaluate (Hz); None selects the
            peak-power bin. An explicit 0.0 means DC, not auto-select.
        t_range (tuple[float, float] | None): (start, stop) in s; None keeps all.
        poloidal_angles (ndarray | None): probe poloidal angles (deg).
        nperseg (int | None): Welch segment length passed to ``cross_spectrum``; None
            uses scipy's default. Set on short ``t_range`` slices to keep averaging.
    Returns:
        result (ModeAtFrequencyResult): per-probe phase/amplitude/coherence with the
            frequency used and the toroidal (and optional poloidal) angles.
    """
    n_probes = signals.shape[0]

    if sample_rate is None:
        sample_rate = round(1.0 / (time[1] - time[0]))

    def prep(sig: NDArray[np.floating]) -> NDArray[np.floating]:
        if t_range is None:
            return sig
        _, out = downsample(time, sig, t_range=t_range, sample_rate=sample_rate)
        return out

    ref_sig = prep(signals[0])
    phases = np.empty(n_probes)
    amplitudes = np.empty(n_probes)
    coherences = np.empty(n_probes)
    phase_errors = np.empty(n_probes)
    amplitude_errors = np.empty(n_probes)

    for i in range(n_probes):
        sig = ref_sig if i == 0 else prep(signals[i])

        result = cross_spectrum(ref_sig, sig, sample_rate, nperseg=nperseg)

        if i == 0 and frequency is None:
            frequency = float(np.round(result.frequency[np.argmax(result.power)]))

        freq_idx = int(np.argmin(np.abs(result.frequency - frequency)))

        phases[i] = result.phase[freq_idx]
        amplitudes[i] = result.power[freq_idx]
        coherences[i] = result.coherence[freq_idx]
        phase_errors[i] = result.phase_error[freq_idx]
        amplitude_errors[i] = result.amplitude_error[freq_idx]

    tor = np.asarray(toroidal_angles, dtype=np.float64)
    phases[phases < 0] += 360.0
    pol = None
    if poloidal_angles is not None:
        pol = np.asarray(poloidal_angles, dtype=np.float64).copy()
        pol[pol < 0] += 360.0

    # The reference probe vs itself is perfectly coherent (γ=1) → 0 phase error,
    # which is a self-reference artifact, not a real measurement. Flag it as NaN so
    # downstream weighting/plots don't treat probe 0 as infinitely certain.
    phase_errors[0] = np.nan
    amplitude_errors[0] = np.nan

    return ModeAtFrequencyResult(
        kind="mode_at_frequency",
        frequency=frequency,
        phase=phases,
        amplitude=amplitudes,
        coherence=coherences,
        toroidal_angle=tor,
        poloidal_angle=pol,
        phase_error=phase_errors,
        amplitude_error=amplitude_errors,
    )


# ---------------------------------------------------------------------------
# Toroidal mode-number fit (phase vs angle)
# ---------------------------------------------------------------------------


def fit_toroidal_mode(
    mode_result: ModeAtFrequencyResult,
    *,
    n_range: tuple[int, int] = (-6, 6),
    weights: str = "amplitude",
) -> ToroidalFitResult:
    """Fit a toroidal mode number to per-probe phase-vs-angle data.

    A rotating mode of toroidal number n imprints a linear phase ramp across the
    toroidal array: ``phase(phi) = c - n * phi`` (deg). Rather than unwrap the
    (mod-360) phases — ill-posed for sparse arrays — this scans integer candidates
    and picks the n whose residual ``phase + n * phi`` clusters most tightly on the
    circle (largest amplitude-weighted resultant). The intercept c is the angle of
    that resultant, giving a wrap-free fit line for the GUI to draw.

    Inputs:
        mode_result (ModeAtFrequencyResult): per-probe phase/amplitude/angle, e.g.
            from ``extract_mode_at_frequency``.
        n_range (tuple[int, int]): inclusive candidate range of toroidal numbers.
        weights ("amplitude" | "coherence" | "uniform"): per-probe fit weighting.
    Returns:
        result (ToroidalFitResult): best-fit n, intercept, and clustering quality.
    """
    phi = np.asarray(mode_result.toroidal_angle, dtype=np.float64)
    phase = np.asarray(mode_result.phase, dtype=np.float64)

    if weights == "coherence":
        w = np.asarray(mode_result.coherence, dtype=np.float64)
    elif weights == "uniform":
        w = np.ones_like(phi)
    else:
        w = np.asarray(mode_result.amplitude, dtype=np.float64)
    # nan_to_num before the all-zero check: a NaN weight survives clip and would
    # silently poison the resultant for every n candidate (NaN > best_R is False).
    w = np.nan_to_num(np.clip(w, 0.0, None), nan=0.0, posinf=0.0, neginf=0.0)
    if not np.any(w > 0):
        w = np.ones_like(phi)

    candidates = list(range(n_range[0], n_range[1] + 1))
    inter = np.empty(len(candidates))   # per-candidate intercept c_n (deg)
    rmag = np.empty(len(candidates))    # per-candidate resultant length
    for j, n in enumerate(candidates):
        resultant = np.sum(w * np.exp(1j * np.deg2rad(phase + n * phi))) / w.sum()
        rmag[j] = np.abs(resultant)
        inter[j] = np.rad2deg(np.angle(resultant))
    best_j = int(np.argmax(rmag))
    best_n, best_R, best_c = candidates[best_j], float(rmag[best_j]), float(inter[best_j])

    # Uncertainty (eigspec-style): propagate per-probe phase σ from the cross-spectral
    # statistics into (a) the intercept's 1σ via inverse-variance combination and
    # (b) a posterior over candidate n from each hypothesis's weighted χ². Falls back
    # to unit σ when phase_error is absent so older callers still get sane numbers.
    sigma = np.asarray(
        mode_result.phase_error if mode_result.phase_error is not None
        else np.full_like(phi, np.nan), dtype=np.float64,
    )
    ok = np.isfinite(sigma) & (sigma > 0)
    fill = float(np.median(sigma[ok])) if np.any(ok) else 1.0
    sigma = np.where(ok, sigma, fill)

    def _wrap180(x):
        return (x + 180.0) % 360.0 - 180.0

    chi2 = np.array([
        np.sum((_wrap180(phase + n * phi - inter[j]) / sigma) ** 2)
        for j, n in enumerate(candidates)
    ])
    post = np.exp(-(chi2 - chi2.min()) / 2.0)
    post /= post.sum()
    n_confidence = float(post[best_j])
    phase_sigma = float(np.sqrt(1.0 / np.sum(1.0 / sigma**2)))

    return ToroidalFitResult(
        kind="toroidal_fit",
        n=int(best_n),
        intercept_deg=best_c % 360.0,
        resultant=best_R,
        frequency=float(mode_result.frequency),
        toroidal_angle=phi,
        phase=phase % 360.0,
        phase_sigma=phase_sigma,
        n_confidence=n_confidence,
    )
