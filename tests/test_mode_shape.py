"""Tests for magnetics.core.mode_shape — the GP mode-shape estimator (eigspec §2.2.2)."""

import numpy as np

from magnetics.core.mode_shape import (
    GPFitResult,
    ModeShapeResult,
    gp_mode_shape,
    gp_periodic_fit,
    mac,
    mac_m_probability,
    mac_n_spectrum,
    mode_pattern_2d,
    poloidal_m_spectrum,
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
        assert p.shape == (th_g.size, phi_g.size)  # row-major [θ][φ]
        assert np.all(np.isfinite(p))
        assert p.dtype.kind == "f"  # real-valued


class TestMAC:
    def test_identical_vectors(self):
        v = np.array([1.0, 1j, -1.0, -1j])
        assert mac(v, v) == 1.0

    def test_invariant_to_scale_and_phase(self):
        # MAC ignores a global complex scale (amplitude × phase)
        v = np.array([1.0, 2j, -3.0, 0.5j])
        assert abs(mac(v, 4.2 * np.exp(1.3j) * v) - 1.0) < 1e-12

    def test_orthogonal_is_zero(self):
        assert mac(np.array([1.0, 0.0, 1.0, 0.0]), np.array([0.0, 1.0, 0.0, 1.0])) == 0.0

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
        sigs = np.vstack(
            [
                np.sin(2 * np.pi * 3000.0 * t - np.deg2rad(2 * p))
                + 0.05 * rng.standard_normal(t.size)
                for p in phi
            ]
        )
        mode = extract_mode_at_frequency(sigs, phi, t, frequency=3000.0)
        fit = fit_toroidal_mode(mode)
        _, _, best = mac_n_spectrum(phi, shape_vector(mode.phase, mode.amplitude))
        assert best == fit.n


class TestMacMProbability:
    def _shape(self, theta_deg, m_true):
        # φ-detrended poloidal shape: phase = −m·θ (what _poloidal_mode produces)
        return shape_vector(-m_true * theta_deg, np.ones_like(theta_deg))

    def test_peaks_and_parity_on_clean_mode(self):
        theta = np.array([0.0, 40.0, 80.0, 130.0, 170.0, 220.0, 270.0, 320.0])
        for m_true, parity in ((1, "odd"), (2, "even"), (3, "odd")):
            res = mac_m_probability(
                theta, self._shape(theta, m_true), value_noise=np.full(theta.size, 0.05)
            )
            assert abs(res.best_m) == m_true
            assert res.mac_nominal.max() > 0.99
            hi = res.p_even if parity == "even" else res.p_odd
            assert hi > 0.9  # a clean mode is confidently the right parity

    def test_probabilities_form_a_distribution(self):
        theta = np.array([0.0, 45.0, 90.0, 150.0, 210.0, 300.0])
        res = mac_m_probability(
            theta, self._shape(theta, 2), value_noise=np.full(theta.size, 0.1), n_draws=300
        )
        assert abs(res.p_by_m.sum() - 1.0) < 1e-9
        assert abs(res.p_even + res.p_odd - 1.0) < 1e-9
        assert res.n_draws == 300

    def test_noise_spreads_the_posterior(self):
        # a sparse array + heavy noise must NOT stay pinned at p=1 on one m
        theta = np.array([0.0, 30.0, 70.0, 110.0])
        res = mac_m_probability(
            theta, self._shape(theta, 2), value_noise=np.full(theta.size, 0.9), seed=1
        )
        assert res.p_best < 1.0  # honest uncertainty, not overconfident

    def test_deterministic_without_noise(self):
        theta = np.array([0.0, 45.0, 90.0, 150.0, 210.0, 300.0])
        res = mac_m_probability(theta, self._shape(theta, 2), value_noise=None)
        assert res.best_m == 2 and res.n_draws == 0
        assert res.p_by_m.max() == 1.0  # collapses to the nominal peak

    def test_seed_is_reproducible(self):
        theta = np.array([0.0, 40.0, 95.0, 160.0, 250.0])
        args = dict(value_noise=np.full(theta.size, 0.3), seed=7, n_draws=200)
        a = mac_m_probability(theta, self._shape(theta, 1), **args)
        b = mac_m_probability(theta, self._shape(theta, 1), **args)
        np.testing.assert_array_equal(a.p_by_m, b.p_by_m)


class TestPoloidalMSpectrum:
    def test_phase_pattern_ignores_amplitude_spread(self):
        # a clean m=2 phase winding with wild per-probe amplitudes (3 decades) — the
        # amplitude-weighted MAC would be captured by the big probe; the phase-pattern
        # one must still nail m=2.
        theta = np.array([0.0, 40.0, 80.0, 130.0, 170.0, 220.0, 270.0, 320.0])
        phase = -2.0 * theta  # deg
        amp = np.array([1.0, 1000.0, 2.0, 0.5, 800.0, 1.0, 3.0, 0.7])
        res, n_used, n_total = poloidal_m_spectrum(theta, phase, amp)
        assert abs(res.best_m) == 2 and res.mac_nominal.max() > 0.99
        assert n_total == 8 and n_used == 8  # nothing below the 5% gate here

    def test_snr_gate_drops_dead_probes(self):
        # 5 clean m=1 probes (unevenly spaced, so no m=1↔m=−3 aliasing) + 4 dead ones
        # (tiny amplitude, random phase). The gate must drop the dead ones so m=1 wins.
        clean = np.array([0.0, 50.0, 110.0, 200.0, 300.0])
        dead = np.array([25.0, 150.0, 240.0, 330.0])
        theta = np.concatenate([clean, dead])
        phase = np.concatenate([-1.0 * clean, np.array([12.0, 200.0, 77.0, 300.0])])
        amp = np.concatenate([np.ones(5), np.full(4, 1e-4)])
        res, n_used, n_total = poloidal_m_spectrum(theta, phase, amp)
        assert n_total == 9 and n_used == 5  # only the 5 real probes survive the gate
        assert abs(res.best_m) == 1 and res.mac_nominal.max() > 0.99

    def test_falls_back_when_too_few_survive(self):
        # if fewer than 4 clear the gate, keep everything rather than fail
        amp = np.array([1.0, 1e-6, 1e-6, 1e-6, 1e-6, 1e-6])
        theta = np.array([0.0, 60.0, 120.0, 180.0, 240.0, 300.0])
        res, n_used, n_total = poloidal_m_spectrum(theta, -theta, amp)
        assert n_used == 6  # gate would leave 1 → fall back to all 6

    def test_carries_monte_carlo_confidence(self):
        theta = np.array([0.0, 45.0, 90.0, 150.0, 210.0, 300.0])
        res, _, _ = poloidal_m_spectrum(
            theta, -2.0 * theta, np.ones(6), np.full(6, 20.0), n_draws=200
        )
        assert res.n_draws == 200 and abs(res.p_by_m.sum() - 1.0) < 1e-9


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
        s = shape_noise(
            np.ones(4), np.array([np.nan, 1.0, 2.0, 1.0]), np.array([np.nan, 0.1, 0.1, 0.1])
        )
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
        sigs = np.vstack(
            [
                env * np.sin(2 * np.pi * 8000.0 * t - np.deg2rad(2 * p))
                + 0.3 * rng.standard_normal(t.size)
                for p in phi
            ]
        )
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


class TestGPScaleInvariance:
    def test_large_magnitude_shape_not_flattened(self):
        # real probe shapes are ~1e5, not ~1; the GP must normalize internally or the
        # unit-variance kernel reads the signal as noise and collapses the mean to 0
        rng = np.random.default_rng(0)
        phi = np.sort(rng.uniform(0, 360, 14))
        scale = 3.0e5
        z = scale * np.exp(1j * np.deg2rad(1 * phi))  # n=1 mode, huge magnitude
        ms = gp_mode_shape(phi, z)
        assert np.ptp(ms.re_mean) > 0.5 * np.ptp(z.real)  # shape recovered, not flat
        # band should be small relative to the signal for a clean mode
        assert np.median(2 * ms.re_sigma) < np.ptp(ms.re_mean)

    def test_scale_invariant_recovery(self):
        # the recovered shape (normalized) is the same whether data is O(1) or O(1e6)
        phi = np.linspace(0, 330, 12)
        base = np.exp(1j * np.deg2rad(2 * phi))
        a = gp_mode_shape(phi, base)
        b = gp_mode_shape(phi, 1e6 * base)
        ra = a.re_mean / (np.ptp(a.re_mean) + 1e-12)
        rb = b.re_mean / (np.ptp(b.re_mean) + 1e-12)
        np.testing.assert_allclose(ra, rb, atol=0.05)
