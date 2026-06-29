"""Tests for magnetics.contract — the GUI⇄analysis spectrogram frame adapter.

Verifies the serialized frames match the shapes in docs/CONTRACT.md: correct keys
and units, a shared (t_ms, f_kHz) grid for spectrogram/n_map, a recoverable
phase_fit n, monotonic streaming progress with one final frame, and that every
payload is JSON-serializable.
"""

import json

import numpy as np

from magnetics.contract import (
    CONTRACT_VERSION,
    _stage_targets,
    build_phase_fit,
    spectrogram_oneshot,
    stream_spectrogram,
)
from magnetics.core.spectral import (
    ToroidalFitResult,
    extract_mode_at_frequency,
    fit_toroidal_mode,
)


# -----------------------------------------------------------------------
# fit_toroidal_mode (physics core)
# -----------------------------------------------------------------------


class TestFitToroidalMode:
    def test_recovers_synthetic_mode_number(self, synthetic_n2):
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 63.0])
        mode = extract_mode_at_frequency(signals, tor, d["time"], frequency=d["f_mode"])
        fit = fit_toroidal_mode(mode)
        assert isinstance(fit, ToroidalFitResult)
        assert fit.kind == "toroidal_fit"
        assert abs(fit.n) == d["n_true"]
        assert fit.resultant > 0.99

    def test_recovers_n_on_dense_array(self):
        n_true = 3
        phis = np.linspace(0, 330, 12)
        phase = (-n_true * phis) % 360.0
        mode = type("M", (), {})()
        mode.toroidal_angle = phis
        mode.phase = phase
        mode.amplitude = np.ones_like(phis)
        mode.coherence = np.ones_like(phis)
        mode.frequency = 5000.0
        fit = fit_toroidal_mode(mode)
        assert fit.n == n_true
        assert fit.resultant > 0.999


# -----------------------------------------------------------------------
# build_phase_fit
# -----------------------------------------------------------------------


class TestBuildPhaseFit:
    def test_shape_and_keys(self, synthetic_n2):
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 63.0])
        pf = build_phase_fit(signals, tor, d["time"], f_khz=d["f_mode"] / 1e3)
        assert set(pf) >= {"phi_deg", "phase_deg", "fit", "n", "f_kHz"}
        assert set(pf["fit"]) == {"phi_deg", "phase_deg"}
        assert pf["fit"]["phi_deg"] == [0.0, 360.0]
        assert len(pf["phi_deg"]) == len(pf["phase_deg"]) == 2
        assert abs(pf["n"]) == d["n_true"]

    def test_explicit_dc_not_auto_detected(self, synthetic_n2):
        # f_khz=0.0 is a real DC request, not the auto-peak sentinel: it must NOT
        # snap to the 3 kHz mode bin.
        d = synthetic_n2
        signals = np.vstack([d["sig1"], d["sig2"]])
        tor = np.array([30.0, 63.0])
        pf = build_phase_fit(signals, tor, d["time"], t0_ms=50.0, f_khz=0.0)
        assert pf["f_kHz"] < 0.5  # stayed at DC, did not auto-select the mode peak


# -----------------------------------------------------------------------
# frame shape / contract conformance
# -----------------------------------------------------------------------


class TestFrameShape:
    def _frame(self, d):
        return spectrogram_oneshot(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        )

    def test_envelope_keys(self, synthetic_n2):
        f = self._frame(synthetic_n2)
        assert set(f) == {"type", "version", "progress", "final", "meta", "data"}
        assert f["type"] == "spectrogram"
        assert f["version"] == CONTRACT_VERSION
        assert f["final"] is True
        assert f["progress"] == 1.0

    def test_spectrogram_block(self, synthetic_n2):
        data = self._frame(synthetic_n2)["data"]
        sg = data["spectrogram"]
        assert set(sg) >= {"t_ms", "f_kHz", "power", "scale"}
        assert sg["scale"] == "linear"
        nf, nt = len(sg["f_kHz"]), len(sg["t_ms"])
        # power oriented [i_f][i_t]
        assert len(sg["power"]) == nf
        assert all(len(row) == nt for row in sg["power"])

    def test_n_map_shares_grid(self, synthetic_n2):
        data = self._frame(synthetic_n2)["data"]
        sg, nm = data["spectrogram"], data["n_map"]
        assert nm["t_ms"] == sg["t_ms"]
        assert nm["f_kHz"] == sg["f_kHz"]
        assert len(nm["n"]) == len(sg["f_kHz"])
        assert all(len(row) == len(sg["t_ms"]) for row in nm["n"])
        # n values are integers
        assert all(isinstance(v, int) for row in nm["n"] for v in row)

    def test_coherence_block(self, synthetic_n2):
        data = self._frame(synthetic_n2)["data"]
        coh = data["coherence"]
        assert coh["f_kHz"] == data["spectrogram"]["f_kHz"]
        assert len(coh["coh"]) == len(coh["f_kHz"])

    def test_units_converted(self, synthetic_n2):
        # synthetic spans 0..0.1 s at 50 kHz → t_ms up to ~100, f_kHz up to 25
        data = self._frame(synthetic_n2)["data"]
        sg = data["spectrogram"]
        assert max(sg["t_ms"]) > 50  # ms, not seconds
        assert max(sg["f_kHz"]) > 10  # kHz, not Hz

    def test_band_crop(self, synthetic_n2):
        d = synthetic_n2
        frame = spectrogram_oneshot(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"],
            slice_duration=0.01, fmin_khz=1.0, fmax_khz=5.0,
        )
        f_khz = frame["data"]["spectrogram"]["f_kHz"]
        assert min(f_khz) >= 1.0
        assert max(f_khz) <= 5.0

    def test_json_serializable(self, synthetic_n2):
        f = self._frame(synthetic_n2)
        s = json.dumps(f)  # must not raise (no numpy scalars / inf / nan keys)
        assert isinstance(s, str)


# -----------------------------------------------------------------------
# streaming
# -----------------------------------------------------------------------


class TestStageTargets:
    def test_no_redundant_final_frame(self):
        # fractions that all clamp at/above the ceiling must collapse to one full frame
        assert _stage_targets((0.15, 0.4, 1.0), ceiling=120) == [18, 48, 120]
        assert _stage_targets((0.15, 0.4, 1.0), ceiling=50) == [8, 20, 50]

    def test_final_is_full_resolution(self):
        for ceiling in (10, 56, 373, 2000):
            assert _stage_targets((0.15, 0.4, 1.0), ceiling)[-1] == ceiling

    def test_dedupes_when_record_too_short(self):
        # a short record (small ceiling) where stages would repeat → no duplicates
        targets = _stage_targets((0.5, 0.8, 1.0), ceiling=3)
        assert targets == sorted(set(targets))
        assert targets[-1] == 3


class TestStreaming:
    def test_progress_monotonic_one_final(self, synthetic_n2):
        d = synthetic_n2
        frames = list(stream_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        ))
        assert len(frames) == 3
        progs = [f["progress"] for f in frames]
        assert progs == sorted(progs)
        assert progs[-1] == 1.0
        assert [f["final"] for f in frames] == [False, False, True]

    def test_frames_share_freq_axis(self, synthetic_n2):
        d = synthetic_n2
        frames = list(stream_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        ))
        f0 = frames[0]["data"]["spectrogram"]["f_kHz"]
        for f in frames[1:]:
            assert f["data"]["spectrogram"]["f_kHz"] == f0

    def test_frames_refine_time_axis(self, synthetic_n2):
        d = synthetic_n2
        frames = list(stream_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
        ))
        widths = [len(f["data"]["spectrogram"]["t_ms"]) for f in frames]
        assert widths[0] <= widths[-1]

    def test_meta_passthrough(self, synthetic_n2):
        d = synthetic_n2
        meta = {"shot": 174446, "t_ms": 3140}
        frames = list(stream_spectrogram(
            d["time"], d["sig1"], d["sig2"], d["delta_phi"],
            slice_duration=0.01, meta=meta,
        ))
        assert all(f["meta"] == meta for f in frames)


# -----------------------------------------------------------------------
# real data
# -----------------------------------------------------------------------


class TestRealData:
    def test_oneshot_on_shot(self, shot_174446):
        d = shot_174446
        delta_phi = d["phi_307"] - d["phi_340"]
        frame = spectrogram_oneshot(
            d["time_s"], d["sig_307"], d["sig_340"], delta_phi,
            slice_duration=0.004, fmin_khz=0.0, fmax_khz=20.0,
            toroidal_angles=np.array([d["phi_307"], d["phi_340"]]),
            signals=np.vstack([d["sig_307"], d["sig_340"]]),
        )
        json.dumps(frame)  # serializable
        sg = frame["data"]["spectrogram"]
        assert max(sg["f_kHz"]) <= 20.0
        assert frame["data"]["phase_fit"]["n"] is not None
        assert len(sg["power"]) == len(sg["f_kHz"])
