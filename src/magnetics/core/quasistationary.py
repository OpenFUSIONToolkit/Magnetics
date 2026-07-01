"""Pure-numpy SLCONTOUR-style quasi-stationary spatial fit.

Ported from analysis/magnetics-code/fit.py — omfit_compat and xarray
removed; only numpy + stdlib. Supports sinusoidal-point and
sinusoidal-integral bases for cylindrical (phi, theta) geometry.

Reference: E. Strait et al., DIII-D magnetics analysis (SLCONTOUR).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ── angular helpers ───────────────────────────────────────────────────────────


def _delta_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Signed angular arc a→b wrapped to (−180, +180]."""
    d = b - a
    return ((d + 180.0) % 360.0) - 180.0


# ── basis function ────────────────────────────────────────────────────────────


def form_basis_function(
    n: int,
    m: int,
    x1: np.ndarray,
    x2: np.ndarray,
    y1: np.ndarray,
    y2: np.ndarray,
    fit_basis: str = "sinusoidal-point",
) -> np.ndarray:
    """Basis-function vector (complex) for mode (n, m).

    x is toroidal phi (degrees), y is poloidal theta (degrees).
    *1/*2 are sensor extents; for the point basis the midpoint is used.

    Ported from magnetics-code/fit.py form_basis_function — omfit_compat
    delta_degrees replaced with _delta_deg.
    """
    dx = _delta_deg(x1, x2)
    dy = _delta_deg(y1, y2)

    if fit_basis == "sinusoidal-point":
        phi_c = x1 + dx / 2.0
        theta_c = y1 + dy / 2.0
        return np.exp(1j * n * np.deg2rad(phi_c) + 1j * m * np.deg2rad(theta_c))

    if fit_basis == "sinusoidal-integral":
        if n == 0 and m == 0:
            return np.ones(len(np.atleast_1d(x1)), dtype=complex)
        if n == 0:
            return (np.exp(1j * m * np.deg2rad(y2)) - np.exp(1j * m * np.deg2rad(y1))) / (
                np.deg2rad(dy) * 1j * m
            )
        if m == 0:
            return (np.exp(1j * n * np.deg2rad(x2)) - np.exp(1j * n * np.deg2rad(x1))) / (
                np.deg2rad(dx) * 1j * n
            )
        return (
            (np.exp(1j * m * np.deg2rad(y2)) - np.exp(1j * m * np.deg2rad(y1)))
            * (np.exp(1j * n * np.deg2rad(x2)) - np.exp(1j * n * np.deg2rad(x1)))
        ) / (np.deg2rad(dx) * np.deg2rad(dy) * (1j * n) * (1j * m))

    raise ValueError(
        f"fit_basis must be 'sinusoidal-point' or 'sinusoidal-integral', got {fit_basis!r}"
    )


# ── result ────────────────────────────────────────────────────────────────────


@dataclass
class FitResult:
    time_ms: np.ndarray  # [n_time]
    ns: np.ndarray  # [n_modes] toroidal mode numbers
    ms: np.ndarray  # [n_modes] poloidal mode numbers
    coeffs: np.ndarray  # complex [n_modes, n_time]
    sigmas: np.ndarray  # complex [n_modes] — Re/Im sigma per mode (time-independent)
    chi_sq: np.ndarray  # [n_time]
    red_chi_sq: np.ndarray  # [n_time]
    condition_number: float
    n_sensors: int


# ── fit ───────────────────────────────────────────────────────────────────────


def fit(
    time_ms: np.ndarray,
    signal: np.ndarray,
    phi_end1: np.ndarray,
    phi_end2: np.ndarray,
    theta_end1: np.ndarray,
    theta_end2: np.ndarray,
    sigma: np.ndarray | None = None,
    ns: tuple[int, ...] = (1, 2, 3),
    ms: tuple[int, ...] = (0,),
    helicity: int = -1,
    fit_basis: str = "sinusoidal-point",
    fit_cond: float = 10.0,
) -> FitResult:
    """SLCONTOUR-style least-squares spatial modal fit.

    Parameters
    ----------
    time_ms   : [n_time]
    signal    : [n_ch, n_time] — measured field values (same units returned)
    phi_end1, phi_end2   : [n_ch] — sensor toroidal extents (degrees)
    theta_end1, theta_end2 : [n_ch] — sensor poloidal extents (degrees)
    sigma     : [n_ch] — measurement noise std; None → uniform 1.0
    ns, ms    : toroidal / poloidal mode numbers to include in the basis
    helicity  : +1 or −1 (DIII-D convention is −1); flips ms sign if needed
    fit_basis : 'sinusoidal-point' or 'sinusoidal-integral'
    fit_cond  : condition-number cutoff (= 1/rcond passed to lstsq)

    Returns FitResult with complex coefficients [n_modes, n_time].
    """
    n_ch, n_time = signal.shape

    if sigma is None:
        sigma = np.ones(n_ch, dtype=float)
    sigma = np.asarray(sigma, dtype=float).copy()
    bad = ~np.isfinite(sigma) | (sigma <= 0)
    if bad.any():
        fill = float(np.nanmean(sigma[~bad])) if np.any(~bad) else 1.0
        sigma[bad] = fill

    ns_arr = np.atleast_1d(ns).astype(int)
    ms_arr = np.atleast_1d(ms).astype(int)

    # Flip m sign to match device helicity convention (ported from fit.py)
    if not np.all(ms_arr == 0) and not np.any(np.sign(ms_arr) == helicity):
        ms_arr = ms_arr * -1

    nms = [(int(n), int(m)) for m in ms_arr for n in ns_arr]

    # ── design matrix A [n_ch, n_cols] ───────────────────────────────────────
    A_cols: list[np.ndarray] = []
    ncomp: list[int] = []

    for n, m in nms:
        fmn = (
            form_basis_function(n, m, phi_end1, phi_end2, theta_end1, theta_end2, fit_basis) / sigma
        )
        if np.allclose(fmn.imag, 0):
            A_cols.append(fmn.real)
            ncomp.append(1)
        else:
            A_cols.append(fmn.real)
            A_cols.append(fmn.imag)
            ncomp.append(2)

    A = np.array(A_cols).T  # [n_ch, n_cols]

    # ── SVD of A — condition number + per-coeff error bars ────────────────────
    _, w_a, Vh_a = np.linalg.svd(A, full_matrices=False)
    raw_cn = float(np.abs(w_a[0] / w_a[-1])) if w_a[-1] != 0.0 else np.inf
    c_a = np.abs(w_a[0] / w_a)
    valid = c_a <= fit_cond

    # ── lstsq across all time slices (vectorised) ─────────────────────────────
    b = signal / sigma[:, None]  # [n_ch, n_time]
    x, _, rank_fit, _ = np.linalg.lstsq(A, b, rcond=1.0 / fit_cond)  # [n_cols, n_time]

    # Per-coeff uncertainty from SVD pseudo-inverse
    w_inv = np.where(valid, 1.0 / np.where(w_a != 0, w_a, 1.0), 0.0)
    fit_sigmas = np.sqrt(np.sum((Vh_a.T * w_inv) ** 2, axis=1))  # [n_cols]

    # ── reform complex coefficients (one complex number per mode) ─────────────
    coeffs_c: list[np.ndarray] = []
    sigmas_c: list[complex] = []
    j = 0
    for nc in ncomp:
        if nc == 1:
            coeffs_c.append(x[j] + 0j)
            sigmas_c.append(complex(fit_sigmas[j]))
        else:
            coeffs_c.append(x[j] + 1j * x[j + 1])
            sigmas_c.append(complex(fit_sigmas[j], fit_sigmas[j + 1]))
        j += nc

    coeffs = np.array(coeffs_c)  # [n_modes, n_time]
    sigmas_out = np.array(sigmas_c)  # [n_modes] complex

    # ── χ² ───────────────────────────────────────────────────────────────────
    fit_signal = (A @ x).real * sigma[:, None]
    residual = signal - fit_signal
    chi_sq = np.sum((residual / sigma[:, None]) ** 2, axis=0)  # [n_time]
    nu = max(n_ch - rank_fit, 1)
    red_chi_sq = chi_sq / nu

    return FitResult(
        time_ms=np.asarray(time_ms, dtype=float),
        ns=np.array([n for n, _ in nms]),
        ms=np.array([m for _, m in nms]),
        coeffs=coeffs,
        sigmas=sigmas_out,
        chi_sq=chi_sq,
        red_chi_sq=red_chi_sq,
        condition_number=raw_cn,
        n_sensors=n_ch,
    )


# ── amplitude / phase extraction ──────────────────────────────────────────────


def amp_phase_with_errors(
    coeff: np.ndarray, sigma: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Amplitude/phase and 1-sigma errors from complex coeff and sigma.

    sigma.real = std of the real part, sigma.imag = std of the imag part.
    Ported from magnetics-code/plots.py _amp_phase_with_errors.

    Returns (amp, amp_err, phase_deg, phase_err_deg).
    """
    c, s = coeff.real, coeff.imag
    ec, es = sigma.real, sigma.imag
    amp = np.sqrt(c**2 + s**2)
    denom = np.where(amp == 0, np.nan, amp)
    amp_err = np.sqrt((c * ec) ** 2 + (s * es) ** 2) / denom
    phase = np.rad2deg(np.arctan2(s, c))
    p2 = np.where((c**2 + s**2) == 0, np.nan, c**2 + s**2)
    phase_err = np.rad2deg(np.sqrt((c * es) ** 2 + (s * ec) ** 2) / p2)
    return amp, np.nan_to_num(amp_err), phase, np.nan_to_num(phase_err)


# ── spatial reconstruction ────────────────────────────────────────────────────


def reconstruct_grid(
    result: FitResult,
    phi_grid: np.ndarray,
    theta_grid: np.ndarray,
    t_idx: int,
) -> np.ndarray:
    """Reconstruct δBp on a (phi, theta) grid at one time index.

    Returns z[n_theta, n_phi] — units match the input signal.
    """
    phi_rad = np.deg2rad(phi_grid)  # [n_phi]
    theta_rad = np.deg2rad(theta_grid)  # [n_theta]
    z = np.zeros((len(theta_grid), len(phi_grid)))
    for i, (n, m) in enumerate(zip(result.ns, result.ms)):
        c = result.coeffs[i, t_idx]
        basis = np.exp(1j * m * theta_rad)[:, None] * np.exp(1j * n * phi_rad)[None, :]
        z += (np.conj(c) * basis).real
    return z
