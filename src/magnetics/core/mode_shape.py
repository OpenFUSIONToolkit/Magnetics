"""Gaussian-process mode-shape estimation with uncertainty (eigspec §2.2.2).

Treat each probe's complex shape-vector component (amplitude·e^{iφ} at one frequency)
as a noisy sample of a smooth, *periodic* plasma eigenmode shape over the toroidal or
poloidal angle. A Gaussian process with a periodic kernel (Olofsson 2014, eqs 16–22)
interpolates that shape onto a fine grid and — crucially — returns a predictive
variance, i.e. the 2σ error band drawn in the paper's figure 10.

The observation noise may be supplied per probe (heteroscedastic), seeded from the
cross-spectral phase/amplitude σ computed in ``spectral`` — so low-coherence probes
widen the band instead of the marginal likelihood guessing a single global noise and
running overconfident on sparse arrays.

Pure numpy/scipy over arrays: no device specifics, no I/O, no GUI concerns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize

from magnetics.core.spectral import (
    extract_mode_at_frequency,
    fit_toroidal_mode,
    mode_from_spectrum,
)


@dataclass(slots=True)
class GPFitResult:
    grid_deg: NDArray[np.floating]  # evaluation grid (deg)
    mean: NDArray[np.floating]  # posterior mean on the grid
    sigma: NDArray[np.floating]  # posterior 1σ on the grid
    length_scale: float  # fitted kernel length scale (rad)
    noise: float  # representative observation noise (σ₁)
    log_marginal_likelihood: float


@dataclass(slots=True)
class ModeShapeResult:
    kind: str  # "mode_shape"
    grid_deg: NDArray[np.floating]
    re_mean: NDArray[np.floating]
    re_sigma: NDArray[np.floating]
    im_mean: NDArray[np.floating]
    im_sigma: NDArray[np.floating]
    amplitude: NDArray[np.floating]  # |re + i·im| of the mean shape
    angle_deg: NDArray[np.floating]  # measured probe angles
    re_obs: NDArray[np.floating]  # measured real parts
    im_obs: NDArray[np.floating]  # measured imaginary parts
    length_scale: float
    noise: float


# ---------------------------------------------------------------------------
# Periodic kernel + GP posterior
# ---------------------------------------------------------------------------


def periodic_kernel(
    a_deg: NDArray[np.floating],
    b_deg: NDArray[np.floating],
    length_scale: float,
) -> NDArray[np.floating]:
    """2π-periodic (exp-sine-squared) kernel matrix between angle sets (eq 17).

    k(x, x') = exp(-2 sin²((x − x')/2) / ℓ²), with x in radians. Periodic by
    construction, so it never imposes a spurious seam at 0/360°.
    """
    a = np.deg2rad(np.asarray(a_deg, dtype=np.float64))[:, None]
    b = np.deg2rad(np.asarray(b_deg, dtype=np.float64))[None, :]
    return np.exp(-2.0 * np.sin((a - b) / 2.0) ** 2 / (length_scale**2))


def _k11(angle_deg, length_scale, noise_var):
    """Training covariance K₁₁ plus the observation-noise diagonal. ``noise_var`` is
    a variance — a scalar (homoscedastic) or one value per probe (heteroscedastic)."""
    k = periodic_kernel(angle_deg, angle_deg, length_scale)
    k[np.diag_indices_from(k)] += np.asarray(noise_var) + 1e-10
    return k


def _posterior(angle_deg, values, grid_deg, length_scale, noise_var):
    """GP posterior mean (eq 20) and 1σ (eq 21) on the grid. ``noise_var`` may be a
    scalar or a per-probe array (seeded from the measured cross-spectral σ)."""
    c = cho_factor(_k11(angle_deg, length_scale, noise_var), lower=True)
    k12 = periodic_kernel(angle_deg, grid_deg, length_scale)  # (m, g)
    mean = k12.T @ cho_solve(c, values)  # eq 20
    var = 1.0 - np.einsum("ij,ij->j", k12, cho_solve(c, k12))  # eq 21 (k₂₂ = 1)
    return mean, np.sqrt(np.clip(var, 0.0, None))


def _neg_log_marginal(log_params, angle_deg, columns, fixed_noise_var=None):
    """Negative log marginal likelihood (eq 22) summed over the data columns (real &
    imaginary share hyper-parameters). With ``fixed_noise_var`` set, only the length
    scale (``log_params[0]``) is free — the noise diagonal is held to the measured
    per-probe variances."""
    length_scale = np.exp(log_params[0])
    noise_var = fixed_noise_var if fixed_noise_var is not None else np.exp(log_params[1]) ** 2
    try:
        c = cho_factor(_k11(angle_deg, length_scale, noise_var), lower=True)
    except np.linalg.LinAlgError:
        return 1e12
    logdet = 2.0 * np.sum(np.log(np.diag(c[0])))
    m = angle_deg.size
    total = 0.0
    for f in columns:
        total += 0.5 * (f @ cho_solve(c, f)) + 0.5 * logdet + 0.5 * m * np.log(2.0 * np.pi)
    return float(total)


def _optimize_hyperparams(angle_deg, columns, ls0, nz0):
    """Maximize the (summed) marginal likelihood over (length_scale, noise)."""
    scale = float(np.std(np.concatenate(columns))) or 1.0
    res = minimize(
        _neg_log_marginal,
        x0=np.log([ls0, max(nz0, 1e-4 * scale)]),
        args=(angle_deg, columns),
        method="Nelder-Mead",
        options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 400},
    )
    ls, nz = np.exp(res.x)
    return float(np.clip(ls, 0.05, 6.0)), float(max(nz, 1e-8))


def _optimize_length_scale(angle_deg, columns, noise_var, ls0=1.0):
    """Maximize the marginal likelihood over the length scale alone, with the noise
    diagonal fixed to the measured per-probe variances."""
    res = minimize(
        _neg_log_marginal,
        x0=np.log([ls0]),
        args=(angle_deg, columns, noise_var),
        method="Nelder-Mead",
        options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 300},
    )
    return float(np.clip(np.exp(res.x[0]), 0.05, 6.0))


def gp_periodic_fit(
    angle_deg: NDArray[np.floating],
    values: NDArray[np.floating],
    *,
    n_grid: int = 181,
    length_scale: float | None = None,
    noise: float | None = None,
    optimize: bool = True,
) -> GPFitResult:
    """Fit one real periodic GP to (angle, value) samples; return mean+σ on a grid.

    Hyper-parameters (length scale, noise) are tuned by maximizing the marginal
    likelihood (eq 22); a pinned value is held fixed and only the free one is tuned.
    Angles in degrees; grid spans [0, 360).
    """
    angle_deg = np.asarray(angle_deg, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    grid = np.linspace(0.0, 360.0, n_grid, endpoint=False)

    ls = length_scale if length_scale is not None else 1.0
    nz = noise if noise is not None else float(np.std(values) * 0.1 + 1e-6)
    if optimize and (length_scale is None or noise is None):
        opt_ls, opt_nz = _optimize_hyperparams(angle_deg, [values], ls, nz)
        ls = opt_ls if length_scale is None else ls  # keep a pinned value pinned
        nz = opt_nz if noise is None else nz

    mean, sigma = _posterior(angle_deg, values, grid, ls, nz**2)
    nll = _neg_log_marginal(np.log([ls, nz]), angle_deg, [values])
    return GPFitResult(grid, mean, sigma, float(ls), float(nz), -nll)


# ---------------------------------------------------------------------------
# Complex mode shape (real + imaginary parts share hyper-parameters)
# ---------------------------------------------------------------------------


def shape_noise(
    amplitude: NDArray[np.floating],
    phase_error_deg: NDArray[np.floating] | None,
    amplitude_error: NDArray[np.floating] | None,
) -> NDArray[np.floating] | None:
    """Per-probe 1σ of the complex shape value from the cross-spectral phase &
    amplitude σ (Tier 1): σ_z² = σ_A² + (A·σ_φ)². Non-finite entries (the reference
    probe) are filled with the median of the rest. Returns None if no errors given."""
    if phase_error_deg is None and amplitude_error is None:
        return None
    a = np.asarray(amplitude, dtype=np.float64)
    s_phi = (
        np.deg2rad(np.nan_to_num(np.asarray(phase_error_deg, dtype=np.float64)))
        if phase_error_deg is not None
        else np.zeros_like(a)
    )
    s_amp = (
        np.nan_to_num(np.asarray(amplitude_error, dtype=np.float64))
        if amplitude_error is not None
        else np.zeros_like(a)
    )
    sigma = np.sqrt(s_amp**2 + (a * s_phi) ** 2)
    ok = np.isfinite(sigma) & (sigma > 0)
    fill = float(np.median(sigma[ok])) if np.any(ok) else float(np.mean(np.abs(a)) * 0.1 + 1e-6)
    return np.where(ok, sigma, fill)


def gp_mode_shape(
    angle_deg: NDArray[np.floating],
    complex_shape: NDArray[np.complexfloating],
    *,
    n_grid: int = 181,
    optimize: bool = True,
    value_noise: NDArray[np.floating] | None = None,
) -> ModeShapeResult:
    """Smooth a complex per-probe shape vector into continuous re/im curves + 2σ.

    The real and imaginary parts are modeled as two GPs sharing one length scale and
    noise (jointly tuned via the marginal likelihood), matching eigspec's treatment of
    the shape vector (eq 15) as a discretized sample of one continuous periodic field.
    Pass ``value_noise`` (per-probe 1σ, e.g. from :func:`shape_noise`) to fix the noise
    diagonal from the measured uncertainty and tune only the length scale — this
    calibrates the band instead of letting the marginal likelihood guess one noise.

    The shape is normalized to unit RMS before the GP (Olofsson 2014 regularizes the
    *unit* shape vector) — the periodic kernel has unit variance, so without this a
    physical-magnitude shape (~10^5 on real probes) reads as all-noise and collapses
    to zero. Outputs are rescaled back to the input units.
    """
    angle_deg = np.asarray(angle_deg, dtype=np.float64)
    z = np.asarray(complex_shape, dtype=np.complex128)
    scale = float(np.sqrt(np.mean(np.abs(z) ** 2)))
    if scale <= 0.0:
        scale = 1.0
    re, im = (z.real / scale).copy(), (z.imag / scale).copy()
    grid = np.linspace(0.0, 360.0, n_grid, endpoint=False)

    if value_noise is not None:
        noise_var = (np.asarray(value_noise, dtype=np.float64) / scale) ** 2
        ls = _optimize_length_scale(angle_deg, [re, im], noise_var) if optimize else 1.0
        nz_report = float(np.sqrt(np.median(noise_var)))
    else:
        ls, nz = 1.0, float(np.std(np.concatenate([re, im])) * 0.1 + 1e-6)
        if optimize:
            ls, nz = _optimize_hyperparams(angle_deg, [re, im], ls, nz)
        noise_var = nz**2
        nz_report = nz

    re_mean, re_sigma = _posterior(angle_deg, re, grid, ls, noise_var)
    im_mean, im_sigma = _posterior(angle_deg, im, grid, ls, noise_var)

    return ModeShapeResult(
        kind="mode_shape",
        grid_deg=grid,
        re_mean=re_mean * scale,
        re_sigma=re_sigma * scale,
        im_mean=im_mean * scale,
        im_sigma=im_sigma * scale,
        amplitude=np.hypot(re_mean, im_mean) * scale,
        angle_deg=angle_deg,
        re_obs=re * scale,
        im_obs=im * scale,
        length_scale=float(ls),
        noise=nz_report * scale,
    )


def shape_vector(
    phase_deg: NDArray[np.floating],
    amplitude: NDArray[np.floating],
) -> NDArray[np.complexfloating]:
    """Per-probe complex shape vector amplitude·e^{iφ} from phase (deg) + amplitude."""
    return np.asarray(amplitude, float) * np.exp(1j * np.deg2rad(np.asarray(phase_deg, float)))


# ---------------------------------------------------------------------------
# Modal Assurance Criterion + shape-based mode identification (eigspec eq 9)
# ---------------------------------------------------------------------------


def mac(v: NDArray[np.complexfloating], w: NDArray[np.complexfloating]) -> float:
    """Modal Assurance Criterion (eq 9): |v†w|² / ((v†v)(w†w)), in [0, 1].

    A phase- and amplitude-independent similarity of two complex shape vectors —
    1 when they describe the same spatial pattern (up to a complex scale), 0 when
    orthogonal. The building block for mode tracking and clustering in eigspec.
    """
    v = np.asarray(v, dtype=np.complex128)
    w = np.asarray(w, dtype=np.complex128)
    den = float(np.real(np.vdot(v, v) * np.vdot(w, w)))
    if den <= 0.0:
        return 0.0
    return float(np.abs(np.vdot(v, w)) ** 2 / den)


def mac_n_spectrum(
    angle_deg: NDArray[np.floating],
    complex_shape: NDArray[np.complexfloating],
    *,
    n_range: tuple[int, int] = (-6, 6),
) -> tuple[NDArray[np.integer], NDArray[np.floating], int]:
    """MAC of a measured shape vector against ideal pure-mode templates e^{−inφ}.

    Gives a *shape-based*, geometry-aware toroidal mode-number identification (how
    closely the measured array pattern resembles each pure rotating mode), a useful
    cross-check on the cross-phase fit. Returns (n_values, mac_values, best_n).
    """
    phi = np.deg2rad(np.asarray(angle_deg, dtype=np.float64))
    z = np.asarray(complex_shape, dtype=np.complex128)
    ns = np.arange(n_range[0], n_range[1] + 1)
    macs = np.array([mac(z, np.exp(-1j * n * phi)) for n in ns])
    return ns, macs, int(ns[int(np.argmax(macs))])


# ---------------------------------------------------------------------------
# Time-resolved mode tracking (eigspec figure 9)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ModeTrackResult:
    kind: str  # "mode_track"
    t_ms: NDArray[np.floating]  # slice-center times (ms)
    mac_to_ref: NDArray[np.floating]  # shape similarity to the reference slice (0–1)
    n_by_time: NDArray[np.integer]  # toroidal n per slice
    ref_t_ms: float  # reference slice time (ms)
    frequency: float  # Hz the track was evaluated at


def track_mode_shape(
    signals: NDArray[np.floating],
    angle_deg: NDArray[np.floating],
    time: NDArray[np.floating],
    *,
    frequency: float,
    n_slices: int = 40,
    window_s: float = 0.002,
    ref_time_s: float | None = None,
    n_range: tuple[int, int] = (-6, 6),
) -> ModeTrackResult:
    """Track the full-array mode over time at a fixed frequency (eigspec fig 9).

    For each of ``n_slices`` time windows, extract the complex array shape and its
    toroidal n, then score each slice's MAC similarity to a reference slice (default:
    the strongest-amplitude slice, so the track is cursor-independent and cacheable).
    A sustained high MAC marks a coherent, persistent mode; drops mark mode changes.
    """
    time = np.asarray(time, dtype=np.float64)
    half = window_s / 2.0
    centers = np.linspace(time[0] + half, time[-1] - half, n_slices)

    shapes, ns, strength = [], [], []
    for tc in centers:
        mode = extract_mode_at_frequency(
            signals, angle_deg, time, frequency=frequency, t_range=(tc - half, tc + half)
        )
        shapes.append(shape_vector(mode.phase, mode.amplitude))
        ns.append(fit_toroidal_mode(mode, n_range=n_range).n)
        strength.append(float(np.sum(np.abs(mode.amplitude))))
    shapes = np.array(shapes)

    ref_idx = (
        int(np.argmin(np.abs(centers - ref_time_s)))
        if ref_time_s is not None
        else int(np.argmax(strength))
    )
    macs = np.array([mac(s, shapes[ref_idx]) for s in shapes])

    return ModeTrackResult(
        kind="mode_track",
        t_ms=centers * 1e3,
        mac_to_ref=macs,
        n_by_time=np.array(ns, dtype=int),
        ref_t_ms=float(centers[ref_idx] * 1e3),
        frequency=float(frequency),
    )


def active_time_window(
    spectrum,
    *,
    power_floor_frac: float = 0.1,
    pad_frac: float = 0.05,
) -> tuple[float, float]:
    """[t_start, t_end] (s) bracketing where the band-integrated array power exceeds
    ``power_floor_frac`` of its peak.

    Time-resolved tracks otherwise span the whole PTDATA record — mostly dead pre/post-
    shot signal — which both wastes time resolution and makes the most-common mode number
    a spurious n=0. Restricting to the active span fixes both. Returns the full span if
    nothing clears the floor. Power is accumulated per probe to avoid materializing the
    full (probe, time, freq) magnitude array.
    """
    t = np.asarray(spectrum.time, dtype=np.float64)
    spec = np.asarray(spectrum.spec)
    env = np.zeros(t.size)
    for p in range(spec.shape[0]):
        env += (np.abs(spec[p]) ** 2).sum(axis=1)  # (n_times,)
    peak = float(env.max()) if env.size else 0.0
    if peak <= 0.0:
        return float(t[0]), float(t[-1])
    active = np.flatnonzero(env >= power_floor_frac * peak)
    if active.size == 0:
        return float(t[0]), float(t[-1])
    t0, t1 = float(t[active[0]]), float(t[active[-1]])
    pad = pad_frac * (t1 - t0)
    return max(float(t[0]), t0 - pad), min(float(t[-1]), t1 + pad)


def _slice_indices(times, n_slices, t_range):
    """Evenly-spaced column indices into ``times``, restricted to ``t_range`` (s) when
    given so a track samples only the active window."""
    lo, hi = 0, times.size - 1
    if t_range is not None:
        sel = np.flatnonzero((times >= t_range[0]) & (times <= t_range[1]))
        if sel.size >= 2:
            lo, hi = int(sel[0]), int(sel[-1])
    return np.unique(np.linspace(lo, hi, min(n_slices, hi - lo + 1)).astype(int))


def track_from_spectrum(
    spectrum,
    angle_deg: NDArray[np.floating],
    frequency: float,
    *,
    n_slices: int = 60,
    t_range: tuple[float, float] | None = None,
    ref_time_s: float | None = None,
    n_range: tuple[int, int] = (-6, 6),
) -> ModeTrackResult:
    """Time-resolved mode track from a precomputed ``ArrayShapeSpectrum`` (the fast
    path used by the service): subsample to ``n_slices`` columns (within ``t_range`` if
    given), read each slice's shape via ``mode_from_spectrum`` (an array index, not a
    fresh STFT), and MAC each to the strongest-amplitude reference. Same result as
    :func:`track_mode_shape`, but the expensive STFT is computed once upstream and shared."""
    times = np.asarray(spectrum.time, dtype=np.float64)
    idx = _slice_indices(times, n_slices, t_range)

    shapes, ns, strength = [], [], []
    for ti in idx:
        mode = mode_from_spectrum(spectrum, angle_deg, float(times[ti]), frequency)
        shapes.append(shape_vector(mode.phase, mode.amplitude))
        ns.append(fit_toroidal_mode(mode, n_range=n_range).n)
        strength.append(float(np.sum(np.abs(mode.amplitude))))
    shapes = np.array(shapes)
    centers = times[idx]

    ref_idx = (
        int(np.argmin(np.abs(centers - ref_time_s)))
        if ref_time_s is not None
        else int(np.argmax(strength))
    )
    macs = np.array([mac(s, shapes[ref_idx]) for s in shapes])

    return ModeTrackResult(
        kind="mode_track",
        t_ms=centers * 1e3,
        mac_to_ref=macs,
        n_by_time=np.array(ns, dtype=int),
        ref_t_ms=float(centers[ref_idx] * 1e3),
        frequency=float(frequency),
    )


@dataclass(slots=True)
class ModeRidgeResult:
    kind: str  # "mode_ridge"
    t_ms: NDArray[np.floating]  # slice-center times (ms)
    n_by_time: NDArray[np.integer]  # best-fit toroidal n of the strongest mode
    freq_khz: NDArray[np.floating]  # dominant in-band frequency per slice (kHz)
    amplitude: NDArray[np.floating]  # array amplitude at the ridge


def ridge_track_from_spectrum(
    spectrum,
    angle_deg: NDArray[np.floating],
    *,
    fmin: float = 1000.0,
    fmax: float = 25000.0,
    n_slices: int = 240,
    t_range: tuple[float, float] | None = None,
    n_range: tuple[int, int] = (-6, 6),
) -> ModeRidgeResult:
    """Best-fit toroidal n vs time, following the *dominant in-band frequency at each
    slice* instead of one global frequency.

    A fixed-frequency n(t) reports only whatever lives in that single bin and is
    meaningless when several modes coexist at different frequencies. Here each slice
    fits n at its own peak-power frequency, so the trace tracks the strongest mode as it
    evolves (and its frequency drifts). This is a 1-D *strongest-mode* summary; the full
    (time, frequency) n-map (``spectral.array_mode_spectrogram``) remains the complete
    view of all simultaneous modes.
    """
    times = np.asarray(spectrum.time, dtype=np.float64)
    freqs = np.asarray(spectrum.freq_band, dtype=np.float64)
    band = np.flatnonzero((freqs >= fmin) & (freqs <= fmax))
    if band.size == 0:
        band = np.arange(freqs.size)
    idx = _slice_indices(times, n_slices, t_range)

    # band-integrated array power Σ_probes|Z|² at just the sampled (slice, band) cells
    spec = np.asarray(spectrum.spec)
    sub = spec[np.ix_(np.arange(spec.shape[0]), idx, band)]  # (n_probes, n_idx, n_band)
    powtf = (np.abs(sub) ** 2).sum(axis=0)  # (n_idx, n_band)

    ns, fkhz, amps = [], [], []
    for j, ti in enumerate(idx):
        f_hz = float(freqs[int(band[int(np.argmax(powtf[j]))])])
        mode = mode_from_spectrum(spectrum, angle_deg, float(times[ti]), f_hz)
        ns.append(fit_toroidal_mode(mode, n_range=n_range).n)
        fkhz.append(f_hz / 1e3)
        amps.append(float(np.sum(np.abs(mode.amplitude))))

    return ModeRidgeResult(
        kind="mode_ridge",
        t_ms=times[idx] * 1e3,
        n_by_time=np.array(ns, dtype=int),
        freq_khz=np.array(fkhz, dtype=float),
        amplitude=np.array(amps, dtype=float),
    )


# ---------------------------------------------------------------------------
# 2-D (θ, φ) modal pattern (eq 23)
# ---------------------------------------------------------------------------


def mode_pattern_2d(
    toroidal: ModeShapeResult,
    poloidal: ModeShapeResult,
) -> tuple[NDArray[np.floating], NDArray[np.floating], NDArray[np.floating]]:
    """Rank-2 (θ, φ) modal pattern from toroidal & poloidal shape estimates (eq 23):

        P(θ, φ) = Re{ (p_re + i·p_im) ⊗ (t_re + i·t_im) }

    Returns (phi_grid_deg, theta_grid_deg, P) with P row-major [i_θ][i_φ] for a contour.
    """
    t = toroidal.re_mean + 1j * toroidal.im_mean  # (n_phi,)
    p = poloidal.re_mean + 1j * poloidal.im_mean  # (n_theta,)
    pattern = np.real(np.outer(p, t))  # (n_theta, n_phi)
    return toroidal.grid_deg, poloidal.grid_deg, pattern
