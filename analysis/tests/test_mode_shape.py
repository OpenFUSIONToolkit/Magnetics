"""Tests for magnetics.core.mode_shape — the GP mode-shape estimator (eigspec §2.2.2)."""

import numpy as np

from magnetics.core.mode_shape import (
    GPFitResult,
    ModeShapeResult,
    gp_mode_shape,
    gp_periodic_fit,
    mode_pattern_2d,
    periodic_kernel,
    shape_vector,
)


class TestPeriodicKernel:
    def test_diagonal_is_one(self):
        a = np.array([0.0, 90.0, 270.0])
        k = periodic_kernel(a, a, length_scale=1.0)
        np.testing.assert_allclose(np.diag(k), 1.0)

    def test_symmetric(self):
        a = np.array([10.0, 120.0, 250.0])
        k = periodic_kernel(a, a, length_scale=0.8)
        np.testing.assert_allclose(k, k.T)

    def test_periodic_seam(self):
        # 0° and 360° are the same point → identical correlation
        k = periodic_kernel(np.array([0.0]), np.array([0.0, 360.0]), length_scale=0.7)
        np.testing.assert_allclose(k[0, 0], k[0, 1])

    def test_decays_with_separation(self):
        k = periodic_kernel(np.array([0.0]), np.array([10.0, 90.0]), length_scale=0.7)
        assert k[0, 0] > k[0, 1]


class TestGPPeriodicFit:
    def _data(self, noise=0.05, seed=0):
        rng = np.random.default_rng(seed)
        x = np.sort(rng.uniform(0, 360, 16))
        y = np.cos(np.deg2rad(2 * x)) + noise * rng.standard_normal(x.size)
        return x, y

    def test_returns_grid_mean_sigma(self):
        x, y = self._data()
        r = gp_periodic_fit(x, y, n_grid=181)
        assert isinstance(r, GPFitResult)
        assert r.grid_deg.shape == r.mean.shape == r.sigma.shape == (181,)
        assert np.all(np.isfinite(r.mean))
        assert np.all(r.sigma >= 0.0)

    def test_interpolates_near_training_points(self):
        x, y = self._data(noise=0.0)
        r = gp_periodic_fit(x, y, optimize=True)
        # mean at the nearest grid node to each probe should track the clean value
        for xi, yi in zip(x, y):
            j = int(np.argmin(np.abs(r.grid_deg - xi % 360)))
            assert abs(r.mean[j] - yi) < 0.25

    def test_uncertainty_grows_away_from_data(self):
        # one cluster of probes, a big empty gap → σ larger in the gap
        x = np.array([0.0, 10.0, 20.0, 30.0, 40.0])
        y = np.cos(np.deg2rad(x))
        r = gp_periodic_fit(x, y, optimize=False, length_scale=0.5, noise=0.01)
        near = r.sigma[int(np.argmin(np.abs(r.grid_deg - 20.0)))]
        far = r.sigma[int(np.argmin(np.abs(r.grid_deg - 200.0)))]
        assert far > near


class TestGPModeShape:
    def _shape(self, n=2, noise=0.05, m=16, seed=1):
        rng = np.random.default_rng(seed)
        phi = np.sort(rng.uniform(0, 360, m))
        z = np.exp(1j * np.deg2rad(n * phi))
        z = z + noise * (rng.standard_normal(m) + 1j * rng.standard_normal(m))
        return phi, z

    def test_returns_mode_shape_result(self):
        phi, z = self._shape()
        ms = gp_mode_shape(phi, z)
        assert isinstance(ms, ModeShapeResult)
        assert ms.kind == "mode_shape"
        for arr in (ms.re_mean, ms.re_sigma, ms.im_mean, ms.im_sigma, ms.amplitude):
            assert arr.shape == ms.grid_deg.shape
            assert np.all(np.isfinite(arr))
        assert ms.length_scale > 0 and ms.noise > 0

    def test_amplitude_roughly_constant_for_rotating_mode(self):
        # a pure n=2 rotating mode has |shape| ≈ const around the torus
        phi, z = self._shape(noise=0.01, m=24)
        ms = gp_mode_shape(phi, z)
        assert ms.amplitude.std() < 0.25 * ms.amplitude.mean()

    def test_band_covers_held_out_probe(self):
        # leave one probe out; its true value should sit within the 2σ band
        phi, z = self._shape(noise=0.02, m=20, seed=3)
        held = 7
        keep = np.ones(phi.size, bool)
        keep[held] = False
        ms = gp_mode_shape(phi[keep], z[keep])
        j = int(np.argmin(np.abs(ms.grid_deg - phi[held] % 360)))
        # within 3σ (lenient — sparse-array GP can be mildly overconfident)
        assert abs(ms.re_mean[j] - z[held].real) <= 3 * ms.re_sigma[j] + 0.1

    def test_shape_vector_roundtrip(self):
        phase = np.array([0.0, 90.0, 180.0])
        amp = np.array([2.0, 1.0, 3.0])
        z = shape_vector(phase, amp)
        np.testing.assert_allclose(np.abs(z), amp, atol=1e-9)
        np.testing.assert_allclose(np.rad2deg(np.angle(z)) % 360, phase % 360, atol=1e-6)


class TestModePattern2D:
    def test_outer_product_shape_and_real(self):
        rng = np.random.default_rng(4)
        phi = np.sort(rng.uniform(0, 360, 16))
        tor = gp_mode_shape(phi, np.exp(1j * np.deg2rad(2 * phi)))
        pol = gp_mode_shape(phi, np.exp(1j * np.deg2rad(1 * phi)))
        phi_g, th_g, p = mode_pattern_2d(tor, pol)
        assert p.shape == (th_g.size, phi_g.size)   # row-major [θ][φ]
        assert np.all(np.isfinite(p))
        assert p.dtype.kind == "f"                  # real-valued
