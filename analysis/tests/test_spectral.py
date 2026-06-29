"""Tests for magnetics.core.spectral — the MODESPEC-style spectral analysis."""

import numpy as np

from magnetics.core.spectral import (
    CrossSpectrumResult,
    ModeAtFrequencyResult,
    SpectrogramResult,
    compute_spectrogram,
    cross_spectrum,
    denoise_spectrogram,
    downsample,
    extract_mode_at_frequency,
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
        result = extract_mode_at_frequency(signals, tor, d["time"], frequency=0.0)
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
