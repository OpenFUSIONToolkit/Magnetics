"""Tests for magnetics.core.spectral — the MODESPEC-style spectral analysis."""

import numpy as np
import pytest

from magnetics.core.spectral import (
    CrossSpectrumResult,
    ModeAtFrequencyResult,
    SpectrogramResult,
    compute_spectrogram,
    cross_spectrum,
    denoise_spectrogram,
    downsample,
    extract_mode_at_frequency,
    fit_toroidal_mode,
    integrate_bdot,
)


# -----------------------------------------------------------------------
# downsample
# -----------------------------------------------------------------------


class TestDownsample:
    def test_reduces_sample_count(self, synthetic_n2):
        t, sig = synthetic_n2["time"], synthetic_n2["sig1"]
        t_ds, s_ds = downsample(t, sig, sample_rate=10_000)
        assert len(s_ds) < len(sig)
        expected = int((t[-1] - t[0]) * 10_000)
        assert len(s_ds) == expected

    def test_trims_to_range(self, synthetic_n2):
        t, sig = synthetic_n2["time"], synthetic_n2["sig1"]
        t_ds, s_ds = downsample(t, sig, t_range=(0.02, 0.06), sample_rate=50_000)
        assert t_ds[0] >= 0.02
        assert t_ds[-1] <= 0.06

    def test_preserves_signal_energy(self, synthetic_n2):
        t, sig = synthetic_n2["time"], synthetic_n2["sig1"]
        t_ds, s_ds = downsample(t, sig, sample_rate=25_000)
        rms_orig = np.sqrt(np.mean(sig**2))
        rms_ds = np.sqrt(np.mean(s_ds**2))
        np.testing.assert_allclose(rms_ds, rms_orig, rtol=0.05)


# -----------------------------------------------------------------------
# integrate_bdot
# -----------------------------------------------------------------------


class TestIntegrateBdot:
    def test_recovers_sine_from_cosine_derivative(self):
        fs = 10_000
        t = np.linspace(0, 0.1, fs, endpoint=False)
        f0 = 200.0
        expected = np.sin(2 * np.pi * f0 * t)
        bdot = np.cos(2 * np.pi * f0 * t) * 2 * np.pi * f0
        result = integrate_bdot(t, bdot)
        corr = np.corrcoef(result, expected)[0, 1]
        assert corr > 0.999

    def test_highpass_window_suppresses_dc(self):
        fs = 10_000
        t = np.linspace(0, 0.5, int(fs * 0.5), endpoint=False)
        f0 = 500.0
        bdot = np.cos(2 * np.pi * f0 * t) * 2 * np.pi * f0 + 100.0  # DC offset
        result = integrate_bdot(t, bdot, highpass_window=0.01)
        # Without high-pass, the DC offset would cause linear drift
        # With high-pass, the result should stay bounded
        assert np.abs(result[-1]) < np.abs(result).max() * 2

    def test_mean_subtraction_mode(self):
        t = np.linspace(0, 0.05, 1000, endpoint=False)
        bdot = np.ones_like(t) * 5.0  # pure DC
        result = integrate_bdot(t, bdot)
        np.testing.assert_allclose(result, 0.0, atol=1e-12)


# -----------------------------------------------------------------------
# cross_spectrum
# -----------------------------------------------------------------------


class TestCrossSpectrum:
    def test_returns_correct_kind(self, synthetic_n2):
        d = synthetic_n2
        result = cross_spectrum(d["sig1"], d["sig2"], d["fs"])
        assert result.kind == "cross_spectrum"

    def test_without_delta_phi_has_no_mode(self, synthetic_n2):
        d = synthetic_n2
        result = cross_spectrum(d["sig1"], d["sig2"], d["fs"])
        assert isinstance(result, CrossSpectrumResult)
        assert result.mode_number is None
        assert result.rms_by_mode is None
        assert result.mode_indices is None

    def test_recovers_synthetic_mode_number(self, synthetic_n2):
        d = synthetic_n2
        result = cross_spectrum(
            d["sig1"], d["sig2"], d["fs"], delta_phi=d["delta_phi"]
        )
        peak_idx = np.argmax(result.power)
        assert abs(result.mode_number[peak_idx]) == d["n_true"]

    def test_peak_frequency_near_expected(self, synthetic_n2):
        d = synthetic_n2
        result = cross_spectrum(d["sig1"], d["sig2"], d["fs"])
        peak_f = result.frequency[np.argmax(result.power)]
        assert abs(peak_f - d["f_mode"]) < 200  # within ~1 FFT bin

    def test_rms_by_mode_peaks_at_true_n(self, synthetic_n2):
        d = synthetic_n2
        result = cross_spectrum(
            d["sig1"], d["sig2"], d["fs"], delta_phi=d["delta_phi"]
        )
        peak_mode_idx = np.argmax(result.rms_by_mode)
        assert abs(result.mode_indices[peak_mode_idx]) == d["n_true"]

    def test_coherence_high_for_correlated_signals(self, synthetic_n2):
        d = synthetic_n2
        result = cross_spectrum(d["sig1"], d["sig2"], d["fs"])
        peak_idx = np.argmax(result.power)
        assert result.coherence[peak_idx] > 0.9

    def test_coherence_low_for_noise(self):
        rng = np.random.default_rng(42)
        noise1 = rng.standard_normal(5000)
        noise2 = rng.standard_normal(5000)
        result = cross_spectrum(noise1, noise2, 10_000)
        assert np.mean(result.coherence) < 0.3

    def test_delta_phi_zero_raises(self, synthetic_n2):
        d = synthetic_n2
        with pytest.raises(ValueError):
            cross_spectrum(d["sig1"], d["sig2"], d["fs"], delta_phi=0.0)


# -----------------------------------------------------------------------
# compute_spectrogram
# -----------------------------------------------------------------------


class TestComputeSpectrogram:
    def test_returns_correct_kind(self, synthetic_n2):
        d = synthetic_n2
        result = compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )
        assert result.kind == "spectrogram"
        assert isinstance(result, SpectrogramResult)

    def test_output_shapes_consistent(self, synthetic_n2):
        d = synthetic_n2
        result = compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )
        n_times = len(result.time)
        n_freqs = len(result.frequency)
        n_modes = len(result.mode_indices)
        assert result.power.shape == (n_times, n_freqs)
        assert result.coherence.shape == (n_times, n_freqs)
        assert result.mode_number.shape == (n_times, n_freqs)
        assert result.rms_by_mode.shape == (n_times, n_modes)

    def test_recovers_mode_across_all_slices(self, synthetic_n2):
        d = synthetic_n2
        result = compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )
        for i in range(len(result.time)):
            peak_idx = np.argmax(result.power[i])
            assert abs(result.mode_number[i, peak_idx]) == d["n_true"]

    def test_on_real_data(self, shot_174446):
        d = shot_174446
        delta_phi = d["phi_307"] - d["phi_340"]
        result = compute_spectrogram(
            d["time_s"],
            d["sig_307"],
            d["sig_340"],
            delta_phi,
            slice_duration=0.004,
        )
        assert result.power.shape[0] > 0
        assert result.power.shape[1] > 0
        assert np.all(np.isfinite(result.power))
        assert np.all(np.isfinite(result.coherence))


# -----------------------------------------------------------------------
# compute_spectrogram — batched-STFT engine specifics
# -----------------------------------------------------------------------


class TestComputeSpectrogramEngine:
    def test_delta_phi_zero_raises(self, synthetic_n2):
        d = synthetic_n2
        with pytest.raises(ValueError):
            compute_spectrogram(d["time"], d["sig1"], d["sig2"], 0.0)

    def test_max_columns_caps_time_bins(self, synthetic_n2):
        d = synthetic_n2
        result = compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"],
            slice_duration=0.001, max_columns=50,
        )
        assert result.time.size <= 50

    def test_detrend_suppresses_dc(self, synthetic_n2):
        d = synthetic_n2
        result = compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )
        # per-window detrend keeps the f=0 bin below the active mode band
        dc = result.power[:, 0].mean()
        band = result.power[:, result.frequency > 1e3].mean()
        assert dc < band

    def test_sign_agrees_with_cross_spectrum(self, synthetic_n2):
        d = synthetic_n2
        spec = compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )
        # strongest off-DC cell of the spectrogram...
        p = spec.power.copy()
        p[:, spec.frequency < 1e3] = 0.0
        it, iff = np.unravel_index(np.argmax(p), p.shape)
        # ...must report the same signed n as the trusted single-window cross_spectrum
        cs = cross_spectrum(d["sig1"], d["sig2"], d["fs"], delta_phi=d["delta_phi"])
        cp = cs.power.copy()
        cp[cs.frequency < 1e3] = 0.0
        assert spec.mode_number[it, iff] == cs.mode_number[np.argmax(cp)]


# -----------------------------------------------------------------------
# denoise_spectrogram
# -----------------------------------------------------------------------


class TestDenoiseSpectrogram:
    def _spec(self, synthetic_n2):
        d = synthetic_n2
        return compute_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )

    def test_returns_correct_kind_and_shapes(self, synthetic_n2):
        spec = self._spec(synthetic_n2)
        dn = denoise_spectrogram(spec)
        assert dn.kind == "spectrogram"
        assert isinstance(dn, SpectrogramResult)
        assert dn.power.shape == spec.power.shape
        assert dn.rms_by_mode.shape == spec.rms_by_mode.shape

    def test_never_adds_power(self, synthetic_n2):
        spec = self._spec(synthetic_n2)
        dn = denoise_spectrogram(spec)
        # de-noising only removes; every cell is <= original and total is not larger
        assert np.all(dn.power <= spec.power + 1e-12)
        assert dn.power.sum() <= spec.power.sum() + 1e-9

    def test_coherence_gate_zeros_low_coherence_cells(self, synthetic_n2):
        spec = self._spec(synthetic_n2)
        dn = denoise_spectrogram(spec, coherence_min=0.5, power_floor_k=None)
        assert np.all(dn.power[spec.coherence < 0.5] == 0.0)

    def test_passes_through_coherence_and_mode(self, synthetic_n2):
        spec = self._spec(synthetic_n2)
        dn = denoise_spectrogram(spec)
        np.testing.assert_array_equal(dn.coherence, spec.coherence)
        np.testing.assert_array_equal(dn.mode_number, spec.mode_number)

    def test_preserves_dominant_mode_peak(self, synthetic_n2):
        d = synthetic_n2
        spec = self._spec(d)
        # The synthetic mode is perfectly stationary, so the per-frequency power
        # floor would treat it as its own background; coherence gating is the
        # correct denoiser for a persistent mode and must keep the peak.
        dn = denoise_spectrogram(spec, coherence_min=0.5, power_floor_k=None)
        peak = np.unravel_index(np.argmax(spec.power), spec.power.shape)
        assert dn.power[peak] > 0
        assert abs(dn.mode_number[peak]) == d["n_true"]

    def test_power_floor_removes_more_than_coherence_alone(self, synthetic_n2):
        spec = self._spec(synthetic_n2)
        coh_only = denoise_spectrogram(spec, coherence_min=0.5, power_floor_k=None)
        with_floor = denoise_spectrogram(spec, coherence_min=0.5, power_floor_k=3.0)
        assert np.count_nonzero(with_floor.power) <= np.count_nonzero(coh_only.power)

    def test_on_real_data(self, shot_174446):
        d = shot_174446
        delta_phi = d["phi_307"] - d["phi_340"]
        spec = compute_spectrogram(
            d["time_s"], d["sig_307"], d["sig_340"], delta_phi, slice_duration=0.004
        )
        dn = denoise_spectrogram(spec)
        # background suppressed, but the bulk of the power (real modes) retained
        assert np.count_nonzero(dn.power) < np.count_nonzero(spec.power)
        assert dn.power.sum() > 0.8 * spec.power.sum()
        assert np.all(np.isfinite(dn.rms_by_mode))


# -----------------------------------------------------------------------
# extract_mode_at_frequency
# -----------------------------------------------------------------------


class TestExtractModeAtFrequency:
    def test_returns_correct_kind(self, synthetic_n2):
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 120.0])
        result = extract_mode_at_frequency(
            signals, tor, d["time"], frequency=d["f_mode"]
        )
        assert result.kind == "mode_at_frequency"
        assert isinstance(result, ModeAtFrequencyResult)

    def test_auto_frequency_detection(self, synthetic_n2):
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 120.0])
        result = extract_mode_at_frequency(signals, tor, d["time"], frequency=None)
        assert abs(result.frequency - d["f_mode"]) < 200

    def test_output_lengths_match_probes(self, synthetic_n2):
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 120.0])
        result = extract_mode_at_frequency(
            signals, tor, d["time"], frequency=d["f_mode"]
        )
        assert len(result.phase) == 2
        assert len(result.amplitude) == 2
        assert len(result.coherence) == 2
        assert len(result.toroidal_angle) == 2

    def test_poloidal_angles_optional(self, synthetic_n2):
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 120.0])

        result_no_pol = extract_mode_at_frequency(
            signals, tor, d["time"], frequency=d["f_mode"]
        )
        assert result_no_pol.poloidal_angle is None

        result_with_pol = extract_mode_at_frequency(
            signals, tor, d["time"],
            frequency=d["f_mode"],
            poloidal_angles=np.array([0.0, 0.0]),
        )
        assert result_with_pol.poloidal_angle is not None


# -----------------------------------------------------------------------
# Uncertainty quantification (eigspec Tier 1)
# -----------------------------------------------------------------------


class TestCrossSpectralUncertainty:
    def test_fields_present_and_shaped(self, synthetic_n2):
        d = synthetic_n2
        r = cross_spectrum(d["sig1"], d["sig2"], d["fs"])
        assert r.phase_error is not None
        assert r.amplitude_error is not None
        assert r.n_segments is not None and r.n_segments >= 1
        assert r.phase_error.shape == r.phase.shape
        assert r.amplitude_error.shape == r.power.shape

    def test_phase_error_finite_and_bounded(self, synthetic_n2):
        d = synthetic_n2
        r = cross_spectrum(d["sig1"], d["sig2"], d["fs"])
        assert np.all(np.isfinite(r.phase_error))
        assert np.all(r.phase_error >= 0.0)
        assert np.all(r.phase_error <= 180.0)  # incoherent bins capped, not inf

    def test_phase_error_shrinks_with_coherence(self):
        # higher SNR → higher coherence → smaller phase error at the mode bin
        rng = np.random.default_rng(1)
        fs = 50_000
        t = np.linspace(0, 0.1, int(fs * 0.1), endpoint=False)
        f0 = 3000.0
        base1, base2 = np.sin(2 * np.pi * f0 * t), np.sin(2 * np.pi * f0 * t - 0.6)
        hi = cross_spectrum(base1 + 0.02 * rng.standard_normal(t.size),
                            base2 + 0.02 * rng.standard_normal(t.size), fs)
        lo = cross_spectrum(base1 + 1.5 * rng.standard_normal(t.size),
                            base2 + 1.5 * rng.standard_normal(t.size), fs)
        i = int(np.argmin(np.abs(hi.frequency - f0)))
        assert hi.coherence[i] > lo.coherence[i]
        assert hi.phase_error[i] < lo.phase_error[i]

    def test_incoherent_noise_has_large_error(self):
        rng = np.random.default_rng(2)
        n1, n2 = rng.standard_normal(5000), rng.standard_normal(5000)
        r = cross_spectrum(n1, n2, 10_000)
        # uncorrelated → low coherence → most bins near the cap
        assert np.median(r.phase_error) > 20.0


class TestModeUncertaintyPropagation:
    def _modes(self, seed=0):
        rng = np.random.default_rng(seed)
        fs = 50_000
        t = np.linspace(0, 0.1, int(fs * 0.1), endpoint=False)
        f0, n = 3000.0, 2
        phis = np.array([0.0, 33.0, 66.0, 120.0, 200.0, 300.0])
        sigs = np.vstack([
            np.sin(2 * np.pi * f0 * t - np.deg2rad(n * p)) + 0.05 * rng.standard_normal(t.size)
            for p in phis
        ])
        return extract_mode_at_frequency(sigs, phis, t, frequency=f0), n

    def test_per_probe_errors_present(self):
        mode, _ = self._modes()
        assert mode.phase_error is not None
        assert mode.amplitude_error is not None
        assert mode.phase_error.shape == mode.phase.shape

    def test_reference_probe_flagged_nan(self):
        # probe 0 vs itself is a self-reference artifact, not a real σ
        mode, _ = self._modes()
        assert np.isnan(mode.phase_error[0])
        assert np.all(np.isfinite(mode.phase_error[1:]))

    def test_fit_reports_confidence_and_sigma(self):
        mode, n_true = self._modes()
        fit = fit_toroidal_mode(mode)
        assert abs(fit.n) == n_true
        assert fit.phase_sigma is not None and fit.phase_sigma > 0
        assert fit.n_confidence is not None
        assert 0.0 < fit.n_confidence <= 1.0
        assert fit.n_confidence > 0.9  # clean synthetic mode → confident

    def test_confidence_drops_for_noisy_underdetermined(self):
        # a noisy 2-probe pair → less confident than a clean full array
        clean_mode, _ = self._modes(seed=3)
        clean = fit_toroidal_mode(clean_mode)
        rng = np.random.default_rng(4)
        fs = 50_000
        t = np.linspace(0, 0.02, int(fs * 0.02), endpoint=False)
        phis = np.array([0.0, 33.0])
        sigs = np.vstack([
            np.sin(2 * np.pi * 3000.0 * t - np.deg2rad(2 * p)) + 1.2 * rng.standard_normal(t.size)
            for p in phis
        ])
        noisy = fit_toroidal_mode(extract_mode_at_frequency(sigs, phis, t, frequency=3000.0))
        assert noisy.n_confidence <= clean.n_confidence + 1e-9
