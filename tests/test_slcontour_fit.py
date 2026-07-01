"""SLCONTOUR basis-function corners (`_slcontour/fit.form_basis_function`).

The `sinusoidal-integral` basis has hand-coded n=0 / m=0 special cases (division by
deg2rad(dx)·in etc.) — exactly where a wrong limit hides. Pin them against the
point basis. `_slcontour` is excluded from lint/typecheck but pytest still runs it.
"""

from __future__ import annotations

import numpy as np
import pytest

from magnetics._slcontour.fit import form_basis_function
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


def test_bad_basis_raises():
    with pytest.raises(OMFITexception):
        form_basis_function(1, 0, 0.0, 1.0, 0.0, 1.0, fit_basis="not-a-basis")
