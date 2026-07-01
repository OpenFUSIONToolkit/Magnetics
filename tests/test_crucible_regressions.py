"""Regression tests for the 2026-07-01 Crucible review fixes.

Each test names one confirmed defect and fails against the pre-fix behavior:
  P3  SVD per-coefficient σ summed the wrong axis (wrong QS error bars)
  P4  toroidal phase_sigma reported the BLUE variance, not the returned estimator's
  P6  the 2D sinusoidal-integral basis was mis-normalized by -180/π for m≠0 modes
  P7  reconstruct_grid used c instead of conj(c) (toroidal mirror); underdetermined
      fits raised IndexError
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from magnetics._slcontour import fit as slfit
from magnetics.core import quasistationary
from magnetics.core.spectral import fit_toroidal_mode


# ── P6: 2D sinusoidal-integral basis normalization ──────────────────────────
def test_slcontour_2d_sinusoidal_integral_basis_is_separable_product():
    """The (n≠0, m≠0) integral basis must equal the product of the two 1D branches.
    Pre-fix it divided by deg2rad(dx*dy)*n*m (π/180 once, no i²), off by -180/π."""
    x1 = np.array([10.0, 100.0])
    x2 = x1 + 20.0
    y1 = np.array([5.0, 60.0])
    y2 = y1 + 15.0
    n, m = 2, 3
    fmn_2d = slfit.form_basis_function(n, m, x1, x2, y1, y2, fit_basis="sinusoidal-integral")
    fmn_n = slfit.form_basis_function(n, 0, x1, x2, y1, y2, fit_basis="sinusoidal-integral")
    fmn_m = slfit.form_basis_function(0, m, x1, x2, y1, y2, fit_basis="sinusoidal-integral")
    assert np.allclose(fmn_2d, fmn_n * fmn_m)


# ── P3: SVD per-coefficient uncertainty axis ────────────────────────────────
def test_svd_covariance_diagonal_sums_the_singular_axis():
    """diag((AᵀA)⁻¹) = Σ_k V[j,k]² / w_k² sums over the singular index (axis=1 of
    Vh.T). The old axis=0 collapsed to 1/w_k² by singular position — not the
    covariance diagonal. Guards the reduction in fit.py:355 and quasistationary.py:173."""
    rng = np.random.default_rng(0)
    a = rng.standard_normal((10, 4))  # non-orthogonal ⇒ condition number ≠ 1
    _, w, vh = np.linalg.svd(a, full_matrices=False)
    w_inv = 1.0 / w
    ref = np.diag(np.linalg.inv(a.T @ a))
    assert np.allclose(np.sum((vh.T * w_inv) ** 2, axis=1), ref)
    assert not np.allclose(np.sum((vh.T * w_inv) ** 2, axis=0), ref)


# ── P7: underdetermined fit must not IndexError (resolved by the axis fix) ───
def test_quasistationary_fit_underdetermined_sizes_sigmas_without_indexerror():
    phi = np.linspace(0.0, 300.0, 6)
    theta = np.linspace(0.0, 150.0, 6)
    signal = np.cos(np.deg2rad(phi))[:, None] + 0.3 * np.sin(np.deg2rad(theta))[:, None]
    res = quasistationary.fit(
        np.array([0.0]),
        signal,
        phi,
        phi,
        theta,
        theta,
        ns=(1, 2, 3),
        ms=(0, 1, 2),  # 9 modes → ~18 basis columns > 6 sensors
        fit_basis="sinusoidal-point",
    )
    assert res.sigmas.shape[0] == res.ns.shape[0]  # one σ per mode; overran before the fix
    assert np.all(np.isfinite(np.abs(res.sigmas)))


# ── P7: reconstruct_grid must not mirror a phase-shifted mode ────────────────
def test_reconstruct_grid_roundtrips_phase_shifted_mode():
    """cos(φ − 40°) fit as n=1, m=0 then reconstructed must reproduce cos(φ − 40°).
    Pre-fix (c instead of conj(c)) it produced cos(φ + 40°) — a toroidal mirror."""
    phi = np.linspace(0.0, 315.0, 8)
    theta0 = np.zeros_like(phi)
    signal = np.cos(np.deg2rad(phi - 40.0))[:, None]  # [n_ch, 1]
    res = quasistationary.fit(
        np.array([0.0]),
        signal,
        phi,
        phi,
        theta0,
        theta0,
        ns=(1,),
        ms=(0,),
        fit_basis="sinusoidal-point",
    )
    grid = np.linspace(0.0, 350.0, 36)
    z = quasistationary.reconstruct_grid(res, grid, np.array([0.0]), 0)  # [1, n_phi]
    assert np.allclose(z[0], np.cos(np.deg2rad(grid - 40.0)), atol=1e-6)


# ── P4: toroidal phase_sigma reflects the actually-returned (weighted) estimator ─
def test_toroidal_phase_sigma_matches_the_weighted_estimator_not_the_blue():
    mode = SimpleNamespace(
        frequency=3000.0,
        toroidal_angle=np.array([0.0, 120.0, 240.0]),
        phase=np.array([0.0, 240.0, 120.0]),
        amplitude=np.array([100.0, 1.0, 1.0]),  # one loud, noisy probe dominates the weight
        coherence=np.array([1.0, 1.0, 1.0]),
        phase_error=np.array([30.0, 3.0, 3.0]),
    )
    fit = fit_toroidal_mode(mode)  # weights="amplitude"
    w, sigma = mode.amplitude, mode.phase_error
    expected = float(np.sqrt(np.sum((w * sigma) ** 2)) / w.sum())
    blue = float(np.sqrt(1.0 / np.sum(1.0 / sigma**2)))  # the old, over-optimistic value
    assert fit.phase_sigma == pytest.approx(expected)
    assert fit.phase_sigma > 5 * blue
