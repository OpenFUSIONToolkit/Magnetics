"""Gaussian-process mode-shape estimation with uncertainty (eigspec §2.2.2).

Treat each probe's complex shape-vector component (amplitude·e^{iφ} at one frequency)
as a noisy sample of a smooth, *periodic* plasma eigenmode shape over the toroidal or
poloidal angle. A Gaussian process with a periodic kernel (Olofsson 2014, eqs 16–22)
interpolates that shape onto a fine grid and — crucially — returns a predictive
variance, i.e. the 2σ error band drawn in the paper's figure 10.

Pure numpy/scipy over arrays: no device specifics, no I/O, no GUI concerns.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize


@dataclass(slots=True)
class GPFitResult:
    grid_deg: NDArray[np.floating]   # evaluation grid (deg)
    mean: NDArray[np.floating]       # posterior mean on the grid
    sigma: NDArray[np.floating]      # posterior 1σ on the grid
    length_scale: float              # fitted kernel length scale (rad)
    noise: float                     # fitted observation noise (σ₁)
    log_marginal_likelihood: float


@dataclass(slots=True)
class ModeShapeResult:
    kind: str                        # "mode_shape"
    grid_deg: NDArray[np.floating]
    re_mean: NDArray[np.floating]
    re_sigma: NDArray[np.floating]
    im_mean: NDArray[np.floating]
    im_sigma: NDArray[np.floating]
    amplitude: NDArray[np.floating]  # |re + i·im| of the mean shape
    angle_deg: NDArray[np.floating]  # measured probe angles
    re_obs: NDArray[np.floating]     # measured real parts
    im_obs: NDArray[np.floating]     # measured imaginary parts
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


def _posterior(
    angle_deg: NDArray[np.floating],
    values: NDArray[np.floating],
    grid_deg: NDArray[np.floating],
    length_scale: float,
    noise: float,
) -> tuple[NDArray[np.floating], NDArray[np.floating], object]:
    """GP posterior mean (eq 20) and variance (eq 21) on the grid, plus the
    Cholesky factor of K₁₁ for reuse by the marginal likelihood."""
    k11 = periodic_kernel(angle_deg, angle_deg, length_scale)
    k11[np.diag_indices_from(k11)] += noise**2 + 1e-10
    c = cho_factor(k11, lower=True)
    k12 = periodic_kernel(angle_deg, grid_deg, length_scale)     # (m, g)
    alpha = cho_solve(c, values)                                  # K₁₁⁻¹ f
    mean = k12.T @ alpha                                          # eq 20
    v = cho_solve(c, k12)                                         # K₁₁⁻¹ k₁₂
    var = 1.0 - np.einsum("ij,ij->j", k12, v)                     # eq 21 (k₂₂ = 1)
    sigma = np.sqrt(np.clip(var, 0.0, None))
    return mean, sigma, c


def _neg_log_marginal(
    log_params: NDArray[np.floating],
    angle_deg: NDArray[np.floating],
    columns: list[NDArray[np.floating]],
) -> float:
    """Negative log marginal likelihood (eq 22) summed over the supplied data
    columns (real & imaginary share one set of hyper-parameters)."""
    length_scale, noise = np.exp(log_params)
    k11 = periodic_kernel(angle_deg, angle_deg, length_scale)
    k11[np.diag_indices_from(k11)] += noise**2 + 1e-10
    try:
        c = cho_factor(k11, lower=True)
    except np.linalg.LinAlgError:
        return 1e12
    logdet = 2.0 * np.sum(np.log(np.diag(c[0])))
    m = angle_deg.size
    total = 0.0
    for f in columns:
        alpha = cho_solve(c, f)
        total += 0.5 * (f @ alpha) + 0.5 * logdet + 0.5 * m * np.log(2.0 * np.pi)
    return float(total)


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
    likelihood (eq 22) unless both are pinned. Angles in degrees; grid spans [0, 360).
    """
    angle_deg = np.asarray(angle_deg, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    grid = np.linspace(0.0, 360.0, n_grid, endpoint=False)

    ls = length_scale if length_scale is not None else 1.0
    nz = noise if noise is not None else float(np.std(values) * 0.1 + 1e-6)
    if optimize and (length_scale is None or noise is None):
        ls, nz = _optimize_hyperparams(angle_deg, [values], ls, nz)

    mean, sigma, c = _posterior(angle_deg, values, grid, ls, nz)
    nll = _neg_log_marginal(np.log([ls, nz]), angle_deg, [values])
    return GPFitResult(grid, mean, sigma, float(ls), float(nz), -nll)


def _optimize_hyperparams(angle_deg, columns, ls0, nz0) -> tuple[float, float]:
    """Maximize the (summed) marginal likelihood over (length_scale, noise)."""
    scale = float(np.std(np.concatenate(columns))) or 1.0
    res = minimize(
        _neg_log_marginal, x0=np.log([ls0, max(nz0, 1e-4 * scale)]),
        args=(angle_deg, columns), method="Nelder-Mead",
        options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 400},
    )
    ls, nz = np.exp(res.x)
    # keep the length scale sane for a 2π-periodic domain
    return float(np.clip(ls, 0.05, 6.0)), float(max(nz, 1e-8))


# ---------------------------------------------------------------------------
# Complex mode shape (real + imaginary parts share hyper-parameters)
# ---------------------------------------------------------------------------


def gp_mode_shape(
    angle_deg: NDArray[np.floating],
    complex_shape: NDArray[np.complexfloating],
    *,
    n_grid: int = 181,
    optimize: bool = True,
) -> ModeShapeResult:
    """Smooth a complex per-probe shape vector into continuous re/im curves + 2σ.

    The real and imaginary parts are modeled as two GPs sharing one length scale and
    noise (jointly tuned via the marginal likelihood), matching eigspec's treatment of
    the shape vector (eq 15) as a discretized sample of one continuous periodic field.
    """
    angle_deg = np.asarray(angle_deg, dtype=np.float64)
    z = np.asarray(complex_shape, dtype=np.complex128)
    re, im = z.real.copy(), z.imag.copy()

    ls, nz = 1.0, float(np.std(np.concatenate([re, im])) * 0.1 + 1e-6)
    if optimize:
        ls, nz = _optimize_hyperparams(angle_deg, [re, im], ls, nz)

    grid = np.linspace(0.0, 360.0, n_grid, endpoint=False)
    re_mean, re_sigma, _ = _posterior(angle_deg, re, grid, ls, nz)
    im_mean, im_sigma, _ = _posterior(angle_deg, im, grid, ls, nz)

    return ModeShapeResult(
        kind="mode_shape",
        grid_deg=grid,
        re_mean=re_mean, re_sigma=re_sigma,
        im_mean=im_mean, im_sigma=im_sigma,
        amplitude=np.hypot(re_mean, im_mean),
        angle_deg=angle_deg, re_obs=re, im_obs=im,
        length_scale=float(ls), noise=float(nz),
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
    t = toroidal.re_mean + 1j * toroidal.im_mean          # (n_phi,)
    p = poloidal.re_mean + 1j * poloidal.im_mean          # (n_theta,)
    pattern = np.real(np.outer(p, t))                      # (n_theta, n_phi)
    return toroidal.grid_deg, poloidal.grid_deg, pattern
