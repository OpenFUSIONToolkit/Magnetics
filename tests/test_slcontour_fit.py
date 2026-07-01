"""SLCONTOUR basis-function corners (`_slcontour/fit.form_basis_function`).

The `sinusoidal-integral` basis has hand-coded n=0 / m=0 special cases (division by
deg2rad(dx)·in etc.) — exactly where a wrong limit hides. Pin them against the
point basis. `_slcontour` is excluded from lint/typecheck but pytest still runs it.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from magnetics._slcontour.fit import fit, form_basis_function
from magnetics._slcontour.omfit_compat import OMFITexception


def test_dc_basis_is_unity():
    # n=0, m=0 → the constant mode is 1 everywhere, both bases.
    val = form_basis_function(0, 0, 10.0, 12.0, 3.0, 5.0, fit_basis="sinusoidal-integral")
    np.testing.assert_allclose(np.real_if_close(val), 1.0)


def test_integral_basis_converges_to_point_for_narrow_extent():
    # As the sensor extent → 0, the integrated basis must approach the point value
    # exp(i n φ) evaluated at the sensor centre.
    n, phi_c = 2, 67.5
    eps = 1e-4
    integral = form_basis_function(
        n, 0, phi_c - eps, phi_c + eps, 0.0, 0.0, fit_basis="sinusoidal-integral"
    )
    point = form_basis_function(
        n, 0, phi_c - eps, phi_c + eps, 0.0, 0.0, fit_basis="sinusoidal-point"
    )
    np.testing.assert_allclose(integral, point, rtol=1e-3)


def test_2d_integral_basis_is_the_product_of_1d_integrals():
    x1 = np.array([10.0, 100.0])
    x2 = x1 + 20.0
    y1 = np.array([5.0, 60.0])
    y2 = y1 + 15.0
    n, m = 2, 3

    two_dim = form_basis_function(n, m, x1, x2, y1, y2, fit_basis="sinusoidal-integral")
    toroidal = form_basis_function(n, 0, x1, x2, y1, y2, fit_basis="sinusoidal-integral")
    poloidal = form_basis_function(0, m, x1, x2, y1, y2, fit_basis="sinusoidal-integral")

    np.testing.assert_allclose(two_dim, toroidal * poloidal)


def test_fit_reports_covariance_diagonal_sigmas():
    phi = np.array([0.0, 45.0, 130.0, 250.0, 310.0])
    sigma = np.array([1.0, 2.0, 1.5, 0.8, 1.3])
    prepared = xr.Dataset(
        {
            "signal": (("channel", "time"), np.zeros((phi.size, 1))),
            "signal_sigma": ("channel", sigma),
            "phi_end1": ("channel", phi),
            "phi_end2": ("channel", phi),
            "theta_end1": ("channel", np.zeros_like(phi)),
            "theta_end2": ("channel", np.zeros_like(phi)),
        },
        coords={"channel": [f"C{i}" for i in range(phi.size)], "time": [0.0]},
        attrs={"device": "synthetic"},
    )

    out = fit(prepared, ns=(1, 2), ms=(0,), fit_basis="sinusoidal-point", verbose=False)

    columns = []
    for n in (1, 2):
        basis = np.exp(1j * n * np.deg2rad(phi)) / sigma
        columns.extend([basis.real, basis.imag])
    design = np.array(columns).T
    expected = np.sqrt(np.diag(np.linalg.inv(design.T @ design)))
    actual = np.array(
        [
            out["fit_sigmas"].isel(mode=0, time=0).values.real,
            out["fit_sigmas"].isel(mode=0, time=0).values.imag,
            out["fit_sigmas"].isel(mode=1, time=0).values.real,
            out["fit_sigmas"].isel(mode=1, time=0).values.imag,
        ]
    )

    np.testing.assert_allclose(actual, expected)


def test_bad_basis_raises():
    with pytest.raises(OMFITexception):
        form_basis_function(1, 0, 0.0, 1.0, 0.0, 1.0, fit_basis="not-a-basis")
