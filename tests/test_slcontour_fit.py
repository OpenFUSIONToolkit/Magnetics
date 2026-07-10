"""SLCONTOUR basis-function corners (`core/qs_fit.form_basis_function`).

The `sinusoidal-integral` basis has hand-coded n=0 / m=0 special cases (division by
deg2rad(dx)·in etc.) — exactly where a wrong limit hides. Pin them against the
point basis.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from magnetics.core.qs_fit import fit, form_basis_function


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
    with pytest.raises(ValueError):
        form_basis_function(1, 0, 0.0, 1.0, 0.0, 1.0, fit_basis="not-a-basis")


# ---------------------------------------------------------------------------
# Gaussian bases — value-pinned against direct numerical integration.
# These branches had NO tests, and this function is exactly where the port
# deliberately diverges from the OMFIT source (its `)(` typo and integral
# scale bugs) — so the intended semantics must be pinned, not inherited.
# ---------------------------------------------------------------------------


class TestGaussianBases:
    X1, X2 = np.array([10.0]), np.array([30.0])  # sensor phi extent (deg)
    Y1, Y2 = np.array([-5.0]), np.array([15.0])  # sensor theta extent (deg)
    NE, ME = 25.0, 30.0  # RBF widths (deg)
    CX, CY = 40.0, 10.0  # RBF centre (deg) — n/m carry the CENTRE for gaussians

    def test_gaussian_point_is_rbf_at_sensor_centre(self):
        v = form_basis_function(
            self.CX,
            self.CY,
            self.X1,
            self.X2,
            self.Y1,
            self.Y2,
            "gaussian-point",
            nepsilon=self.NE,
            mepsilon=self.ME,
        )
        xc, yc = 20.0, 5.0  # midpoints of the extents
        expect = np.exp(-(((self.CX - xc) / self.NE) ** 2 + ((self.CY - yc) / self.ME) ** 2))
        assert v.dtype.kind == "f"
        assert v[0] == pytest.approx(expect, rel=1e-12)

    def test_gaussian_point_uniform_direction_drops_term(self):
        # mepsilon=inf → ridge in phi only (theta term contributes nothing)
        v = form_basis_function(
            self.CX,
            999.0,
            self.X1,
            self.X2,
            self.Y1,
            self.Y2,
            "gaussian-point",
            nepsilon=self.NE,
            mepsilon=np.inf,
        )
        assert v[0] == pytest.approx(np.exp(-(((self.CX - 20.0) / self.NE) ** 2)), rel=1e-12)

    def test_gaussian_point_periodic_copies_wrap(self):
        # centre at 350°, sensor centred at 20°: the +360° copy (cx=710? no — cx-360=-10)
        # sits 30° away and dominates the direct 330° separation.
        base = form_basis_function(
            350.0,
            self.CY,
            self.X1,
            self.X2,
            self.Y1,
            self.Y2,
            "gaussian-point",
            ncycle=0,
            nepsilon=self.NE,
            mepsilon=self.ME,
        )
        wrapped = form_basis_function(
            350.0,
            self.CY,
            self.X1,
            self.X2,
            self.Y1,
            self.Y2,
            "gaussian-point",
            ncycle=1,
            nepsilon=self.NE,
            mepsilon=self.ME,
        )
        manual = sum(
            np.exp(
                -((((350.0 + k * 360) - 20.0) / self.NE) ** 2 + ((self.CY - 5.0) / self.ME) ** 2)
            )
            for k in (-1, 0, 1)
        )
        assert wrapped[0] == pytest.approx(manual, rel=1e-12)
        assert wrapped[0] > base[0] * 10  # the wrap matters physically

    def test_gaussian_integral_2d_matches_dblquad(self):
        from scipy.integrate import dblquad

        v = form_basis_function(
            self.CX,
            self.CY,
            self.X1,
            self.X2,
            self.Y1,
            self.Y2,
            "gaussian-integral",
            nepsilon=self.NE,
            mepsilon=self.ME,
        )
        num, _ = dblquad(
            lambda y, x: np.exp(-(((x - self.CX) / self.NE) ** 2 + ((y - self.CY) / self.ME) ** 2)),
            float(self.X1[0]),
            float(self.X2[0]),
            float(self.Y1[0]),
            float(self.Y2[0]),
        )
        # the basis IS the plain area integral of the RBF over the sensor extent
        assert v[0] == pytest.approx(num, rel=1e-10)

    @pytest.mark.parametrize("uniform", ["theta", "phi"])
    def test_gaussian_integral_ridge_matches_quad(self, uniform):
        from scipy.integrate import quad

        if uniform == "theta":  # mepsilon=inf → 1-D line integral along phi
            v = form_basis_function(
                self.CX,
                0.0,
                self.X1,
                self.X2,
                self.Y1,
                self.Y2,
                "gaussian-integral",
                nepsilon=self.NE,
                mepsilon=np.inf,
            )
            num, _ = quad(
                lambda x: np.exp(-(((x - self.CX) / self.NE) ** 2)),
                float(self.X1[0]),
                float(self.X2[0]),
            )
        else:  # nepsilon=inf → 1-D line integral along theta
            v = form_basis_function(
                0.0,
                self.CY,
                self.X1,
                self.X2,
                self.Y1,
                self.Y2,
                "gaussian-integral",
                nepsilon=np.inf,
                mepsilon=self.ME,
            )
            num, _ = quad(
                lambda y: np.exp(-(((y - self.CY) / self.ME) ** 2)),
                float(self.Y1[0]),
                float(self.Y2[0]),
            )
        assert v[0] == pytest.approx(num, rel=1e-10)

    def test_sinusoidal_integral_mixed_mode_is_exact_area_average(self):
        """The (n≠0, m≠0) sinusoidal-integral value must be the exact area-average
        of e^{i(nφ+mθ)} over the sensor extent. This is the site where the port
        DELIBERATELY diverges from OMFIT (whose expression is off by −180/π); the
        divergence is intentional and this pins the correct semantics."""
        from scipy.integrate import dblquad

        n_mode, m_mode = 2, 1
        v = form_basis_function(
            n_mode, m_mode, self.X1, self.X2, self.Y1, self.Y2, "sinusoidal-integral"
        )
        area = np.deg2rad(self.X2[0] - self.X1[0]) * np.deg2rad(self.Y2[0] - self.Y1[0])

        def integrand(re):
            def f(y, x):
                val = np.exp(1j * (n_mode * np.deg2rad(x) + m_mode * np.deg2rad(y)))
                return val.real if re else val.imag

            num, _ = dblquad(
                f, float(self.X1[0]), float(self.X2[0]), float(self.Y1[0]), float(self.Y2[0])
            )
            return num

        # ∫∫ over degrees × (rad/deg)² = ∫∫ over radians; divide by the rad² area
        avg = (integrand(True) + 1j * integrand(False)) * np.deg2rad(1.0) ** 2 / area
        assert v[0].real == pytest.approx(avg.real, rel=1e-9)
        assert v[0].imag == pytest.approx(avg.imag, rel=1e-9)
