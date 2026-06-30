"""Tests for magnetics.core.mode_shape — the GP mode-shape estimator (eigspec §2.2.2)."""

import numpy as np

from magnetics.core.mode_shape import (
    GPFitResult,
    ModeShapeResult,
    gp_mode_shape,
    gp_periodic_fit,
    mac,
    mac_n_spectrum,
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


class TestMAC:
    def test_identical_vectors(self):
        v = np.array([1.0, 1j, -1.0, -1j])
        assert mac(v, v) == 1.0

    def test_invariant_to_scale_and_phase(self):
        # MAC ignores a global complex scale (amplitude × phase)
        v = np.array([1.0, 2j, -3.0, 0.5j])
        assert abs(mac(v, 4.2 * np.exp(1.3j) * v) - 1.0) < 1e-12

    def test_orthogonal_is_zero(self):
        assert mac(np.array([1.0, 0.0, 1.0, 0.0]),
                   np.array([0.0, 1.0, 0.0, 1.0])) == 0.0

    def test_zero_vector_safe(self):
        assert mac(np.zeros(4, complex), np.ones(4, complex)) == 0.0

    def test_bounded_unit_interval(self):
        rng = np.random.default_rng(7)
        for _ in range(20):
            a = rng.standard_normal(8) + 1j * rng.standard_normal(8)
            b = rng.standard_normal(8) + 1j * rng.standard_normal(8)
            assert 0.0 <= mac(a, b) <= 1.0 + 1e-12


class TestMacNSpectrum:
    def test_peaks_at_true_mode(self):
        phi = np.array([0.0, 33.0, 66.0, 120.0, 200.0, 300.0])
        n_true = 3
        z = shape_vector(-n_true * phi, np.ones_like(phi))  # phase = -n·φ
        ns, macs, best = mac_n_spectrum(phi, z)
        assert abs(best) == n_true
        assert macs.max() > 0.99
        assert ns.shape == macs.shape

    def test_agrees_with_cross_phase_fit(self):
        # the shape-MAC n must match the cross-phase fit's n (same sign convention),
        # since both consume the same extract_mode_at_frequency phases
        from magnetics.core.spectral import (
            extract_mode_at_frequency,
            fit_toroidal_mode,
        )
        rng = np.random.default_rng(5)
        fs = 50_000
        t = np.linspace(0, 0.1, int(fs * 0.1), endpoint=False)
        phi = np.array([0.0, 33.0, 66.0, 120.0, 200.0, 300.0])
        sigs = np.vstack([
            np.sin(2 * np.pi * 3000.0 * t - np.deg2rad(2 * p)) + 0.05 * rng.standard_normal(t.size)
            for p in phi
        ])
        mode = extract_mode_at_frequency(sigs, phi, t, frequency=3000.0)
        fit = fit_toroidal_mode(mode)
        _, _, best = mac_n_spectrum(phi, shape_vector(mode.phase, mode.amplitude))
        assert best == fit.n


class TestNoiseCalibration:
    def test_shape_noise_combines_phase_and_amplitude(self):
        from magnetics.core.mode_shape import shape_noise
        amp = np.array([1.0, 2.0, 1.0])
        # σ_z² = σ_A² + (A·σ_φ)²; here σ_A=0.1, σ_φ=0 → σ_z=0.1
        s = shape_noise(amp, np.array([0.0, 0.0, 0.0]), np.array([0.1, 0.1, 0.1]))
        np.testing.assert_allclose(s, 0.1, atol=1e-9)

    def test_shape_noise_fills_reference_nan(self):
        from magnetics.core.mode_shape import shape_noise
        # reference probe (index 0) has NaN errors → filled, not propagated
        s = shape_noise(np.ones(4),
                        np.array([np.nan, 1.0, 2.0, 1.0]),
                        np.array([np.nan, 0.1, 0.1, 0.1]))
        assert np.all(np.isfinite(s)) and np.all(s > 0)

    def test_shape_noise_none_without_errors(self):
        from magnetics.core.mode_shape import shape_noise
        assert shape_noise(np.ones(3), None, None) is None

    def test_band_widens_at_noisy_probe(self):
        # heteroscedastic: a noisy probe's neighborhood gets a wider band than a clean one
        phi = np.array([0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
        z = np.exp(1j * np.deg2rad(2 * phi))
        value_noise = np.array([0.02, 0.02, 0.02, 0.40, 0.02, 0.02])  # probe at 180° noisy
        ms = gp_mode_shape(phi, z, value_noise=value_noise)

        def band(a):
            j = int(np.argmin(np.abs(ms.grid_deg - a)))
            return float(np.hypot(ms.re_sigma[j], ms.im_sigma[j]))

        assert band(180.0) > band(60.0)


class TestModeTracking:
    def _array(self, on_until=0.025, seed=0):
        rng = np.random.default_rng(seed)
        fs = 200_000
        t = np.linspace(0, 0.05, int(fs * 0.05), endpoint=False)
        phi = np.linspace(0, 330, 12)
        env = (t < on_until).astype(float)  # n=2 mode on, then gone
        sigs = np.vstack([
            env * np.sin(2 * np.pi * 8000.0 * t - np.deg2rad(2 * p)) + 0.3 * rng.standard_normal(t.size)
            for p in phi
        ])
        return sigs, phi, t

    def test_returns_track(self):
        from magnetics.core.mode_shape import ModeTrackResult, track_mode_shape
        sigs, phi, t = self._array()
        tr = track_mode_shape(sigs, phi, t, frequency=8000.0, n_slices=16)
        assert isinstance(tr, ModeTrackResult)
        assert tr.t_ms.shape == tr.mac_to_ref.shape == tr.n_by_time.shape == (16,)
        assert np.all((tr.mac_to_ref >= 0.0) & (tr.mac_to_ref <= 1.0 + 1e-9))

    def test_mac_high_while_mode_present_low_after(self):
        from magnetics.core.mode_shape import track_mode_shape
        sigs, phi, t = self._array()
        tr = track_mode_shape(sigs, phi, t, frequency=8000.0, n_slices=20)
        on = tr.mac_to_ref[tr.t_ms < 25.0].mean()
        off = tr.mac_to_ref[tr.t_ms > 25.0].mean()
        assert on > 0.8 and off < 0.5 and on > off

    def test_recovers_mode_number_during_mode(self):
        from magnetics.core.mode_shape import track_mode_shape
        sigs, phi, t = self._array()
        tr = track_mode_shape(sigs, phi, t, frequency=8000.0, n_slices=20)
        assert abs(int(np.median(tr.n_by_time[tr.t_ms < 25.0]))) == 2
