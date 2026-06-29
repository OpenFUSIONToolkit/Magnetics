"""MODESPEC-style rotating-mode spectral analysis.

Translated from OMFIT's spectrogram_prep.py and spectrogram_useful_stuff.py.
Pure functions over numpy arrays — no device-specific data access, no GUI concerns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import cumulative_trapezoid
from scipy.ndimage import uniform_filter1d
from scipy.signal import coherence as scipy_coherence
from scipy.signal import csd, resample


@dataclass(slots=True)
class CrossSpectrumResult:
    kind: str
    frequency: NDArray[np.floating]
    power: NDArray[np.floating]
    coherence: NDArray[np.floating]
    phase: NDArray[np.floating]
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


def cross_spectrum(
    sig1: NDArray[np.floating],
    sig2: NDArray[np.floating],
    sample_rate: float,
    *,
    delta_phi: float | None = None,
) -> CrossSpectrumResult:
    """2-point cross-power spectral density, coherence, and phase between two probes.
    With delta_phi, also returns mode number n = round(phase / delta_phi) and per-mode RMS.

    Inputs:
        sig1 (ndarray): first probe time series.
        sig2 (ndarray): second probe time series.
        sample_rate (float): sampling rate (Hz).
        delta_phi (float | None): toroidal separation (deg); enables mode-number output.
    Returns:
        result (CrossSpectrumResult): frequency/power/coherence/phase, plus
            mode_number/rms_by_mode/mode_indices set iff delta_phi is given.
    """
    f, pxy = csd(sig2, sig1, fs=sample_rate)
    _, coh = scipy_coherence(sig2, sig1, fs=sample_rate)

    power = np.abs(pxy)
    phase = np.rad2deg(np.angle(pxy))

    if delta_phi is None:
        return CrossSpectrumResult(
            kind="cross_spectrum",
            frequency=f,
            power=power,
            coherence=coh,
            phase=phase,
        )

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
        mode_number=mode,
        rms_by_mode=rms,
        mode_indices=mode_indices,
    )


# ---------------------------------------------------------------------------
# Sliding-window spectrogram
# ---------------------------------------------------------------------------


def compute_spectrogram(
    time: NDArray[np.floating],
    sig1: NDArray[np.floating],
    sig2: NDArray[np.floating],
    delta_phi: float,
    *,
    slice_duration: float = 0.001,
) -> SpectrogramResult:
    """Sliding-window spectrogram with 50% overlap, calling cross_spectrum per window.

    Inputs:
        time (ndarray): sample times (s).
        sig1 (ndarray): first probe time series.
        sig2 (ndarray): second probe time series.
        delta_phi (float): toroidal separation (deg).
        slice_duration (float): FFT window width (s).
    Returns:
        result (SpectrogramResult): power/coherence/mode_number as (n_times, n_freqs)
            arrays, with time/frequency/rms_by_mode/mode_indices.
    """
    nx = len(time)
    dt = (time[-1] - time[0]) / (nx - 1)
    samples_per_slice = int(np.round(slice_duration / dt))
    sample_rate = round(1.0 / dt)

    # 50 % overlap → step = half a slice
    n_slices = (nx - samples_per_slice) * 2 // samples_per_slice + 1
    starts = np.arange(n_slices, dtype=np.intp) * (samples_per_slice // 2)
    t_centers = time[starts] + slice_duration / 2.0

    # Run the first slice to discover output shapes
    first = cross_spectrum(
        sig1[starts[0] : starts[0] + samples_per_slice - 1],
        sig2[starts[0] : starts[0] + samples_per_slice - 1],
        sample_rate,
        delta_phi=delta_phi,
    )
    n_freqs = len(first.frequency)
    n_modes = len(first.mode_indices)

    power = np.empty((n_slices, n_freqs))
    coh = np.empty((n_slices, n_freqs))
    mode = np.empty((n_slices, n_freqs), dtype=np.intp)
    rms = np.empty((n_slices, n_modes))

    power[0] = first.power
    coh[0] = first.coherence
    mode[0] = first.mode_number
    rms[0] = first.rms_by_mode

    for idx in range(1, n_slices):
        i = starts[idx]
        result = cross_spectrum(
            sig1[i : i + samples_per_slice - 1],
            sig2[i : i + samples_per_slice - 1],
            sample_rate,
            delta_phi=delta_phi,
        )
        power[idx] = result.power
        coh[idx] = result.coherence
        mode[idx] = result.mode_number
        rms[idx] = result.rms_by_mode

    return SpectrogramResult(
        kind="spectrogram",
        time=t_centers,
        frequency=first.frequency,
        power=power,
        coherence=coh,
        mode_number=mode,
        rms_by_mode=rms,
        mode_indices=first.mode_indices,
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
# Multi-probe mode extraction at a single frequency
# ---------------------------------------------------------------------------


def extract_mode_at_frequency(
    signals: NDArray[np.floating],
    toroidal_angles: NDArray[np.floating],
    time: NDArray[np.floating],
    *,
    sample_rate: float | None = None,
    frequency: float = 0.0,
    t_range: tuple[float, float] | None = None,
    poloidal_angles: NDArray[np.floating] | None = None,
) -> ModeAtFrequencyResult:
    """Phase, amplitude, and coherence at one frequency for each probe vs. the first,
    for phase-vs-angle mode fitting; frequency=0 picks the reference's peak-power bin.

    Inputs:
        signals (ndarray): probe time series, shape (n_probes, n_samples).
        toroidal_angles (ndarray): probe toroidal angles (deg).
        time (ndarray): sample times (s).
        sample_rate (float | None): sampling rate (Hz); inferred from time if None.
        frequency (float): frequency to evaluate (Hz); 0 selects the peak-power bin.
        t_range (tuple[float, float] | None): (start, stop) in s; None keeps all.
        poloidal_angles (ndarray | None): probe poloidal angles (deg).
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

    for i in range(n_probes):
        sig = ref_sig if i == 0 else prep(signals[i])

        result = cross_spectrum(ref_sig, sig, sample_rate)

        if i == 0 and frequency == 0.0:
            frequency = float(np.round(result.frequency[np.argmax(result.power)]))

        freq_idx = int(np.argmin(np.abs(result.frequency - frequency)))

        phases[i] = result.phase[freq_idx]
        amplitudes[i] = result.power[freq_idx]
        coherences[i] = result.coherence[freq_idx]

    tor = np.asarray(toroidal_angles, dtype=np.float64)
    phases[phases < 0] += 360.0
    pol = None
    if poloidal_angles is not None:
        pol = np.asarray(poloidal_angles, dtype=np.float64).copy()
        pol[pol < 0] += 360.0

    return ModeAtFrequencyResult(
        kind="mode_at_frequency",
        frequency=frequency,
        phase=phases,
        amplitude=amplitudes,
        coherence=coherences,
        toroidal_angle=tor,
        poloidal_angle=pol,
    )
