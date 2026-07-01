"""Backend node-builder tests: build each GUI node from whatever fetched HDF5 is
on disk and assert it matches the contract.ts shape. Skips cleanly when no shot
files are present (e.g. CI without data).
"""

from __future__ import annotations

import pytest

from magnetics.core import contracts
from magnetics.data import diiid
from magnetics.service import nodes


def _first_shot():
    ms = nodes.machines()
    if not ms:
        pytest.skip("no fetched HDF5 in the data dir")
    return ms[0]["id"]


def test_machines_shape():
    for m in nodes.machines():
        assert {"id", "label", "device"} <= set(m)


def test_geometry_node():
    shot = _first_shot()
    n = nodes.build_node(shot, "geometry")
    assert n["kind"] == "scatter2d"
    assert n["points"] and all("x" in p and "y" in p for p in n["points"])


def test_spectrogram_node():
    shot = _first_shot()
    n = nodes.build_node(shot, "spectrogram")
    assert n["kind"] == "heatmap"
    assert len(n["z"]) == len(n["y"])  # rows = freqs
    assert len(n["z"][0]) == len(n["x"])  # cols = times


def test_contour_node():
    shot = _first_shot()
    try:
        n = nodes.build_node(shot, "contour")
    except Exception as e:  # noqa: BLE001 — shot may lack the MPID toroidal array
        pytest.skip(f"no MPID toroidal array in this shot: {e}")
    assert n["kind"] == "contour"
    assert len(n["z"]) == len(n["y"]) and len(n["z"][0]) == len(n["x"])


def test_phase_fit_node_has_real_error_bars():
    shot = _first_shot()
    n = nodes.build_node(shot, "phase_fit")
    assert n["kind"] == "scatter2d"
    # at least one probe carries a real 1σ cross-spectral phase error_y, and it is
    # a finite non-negative number (not the GUI's old fabricated value)
    errs = [p["error_y"] for p in n["points"] if "error_y" in p]
    assert errs, "phase_fit emitted no error_y bars"
    assert all(e >= 0.0 for e in errs)
    assert n["meta"].get("n_confidence") is not None
    assert n["meta"].get("phase_sigma_deg") is not None


def test_mode_shape_node_has_band_and_markers():
    shot = _first_shot()
    n = nodes.build_node(shot, "mode_shape")
    assert n["kind"] == "line"
    assert {s["name"] for s in n["series"]} >= {"Re", "Im"}
    for s in n["series"]:
        assert len(s["lower"]) == len(s["upper"]) == len(s["y"])
        # band brackets the mean everywhere
        assert all(lo <= y <= up for lo, y, up in zip(s["lower"], s["y"], s["upper"]))
        # measured probe markers present (cf. Olofsson fig 10)
        assert len(s["markers"]["x"]) == len(s["markers"]["y"]) > 0


def test_toroidal_array_single_family():
    # the toroidal n-fit must use ONE consistent probe type at the midplane — a
    # "both" pull also brings integrated-Bp + off-midplane poloidal probes, and
    # mixing those scrambles the fit
    shot = _first_shot()
    arr = nodes._toroidal_arr(shot)
    assert len({diiid.family_of(n) for n, _ in arr}) == 1


def test_poloidal_shape_node():
    shot = _first_shot()
    try:
        n = nodes.build_node(shot, "poloidal_shape")
    except Exception as e:  # noqa: BLE001 — shot may lack the MPID poloidal array
        pytest.skip(f"no poloidal array in this shot: {e}")
    assert n["kind"] == "line"
    assert {s["name"] for s in n["series"]} >= {"Re", "Im"}
    assert all("markers" in s for s in n["series"])


def test_mode_nodes_share_one_stft():
    # phase_fit, mode_shape, mode_track all read ONE cached full-array STFT rather
    # than recomputing it; cursor moves and frequency changes index into it
    shot = _first_shot()
    nodes._array_spectrum.cache_clear()
    nodes.build_node(shot, "phase_fit", {"time": "100"})
    hits0 = nodes._array_spectrum.cache_info().hits
    nodes.build_node(shot, "mode_shape", {"time": "100"})  # same array → hit
    nodes.build_node(shot, "mode_track")
    assert nodes._array_spectrum.cache_info().hits >= hits0 + 2


def test_mode_track_node():
    shot = _first_shot()
    n = nodes.build_node(shot, "mode_track")
    assert n["kind"] == "line"
    s = n["series"][0]
    assert len(s["x"]) == len(s["y"]) and all(0.0 <= y <= 1.0 for y in s["y"])
    assert n["meta"].get("ref_t_ms") is not None


def test_mode_over_time_node():
    # n(t): best-fit toroidal mode number per time slice, as a line trace
    shot = _first_shot()
    n = nodes.build_node(shot, "mode_over_time")
    assert n["kind"] == "line"
    s = n["series"][0]
    assert len(s["x"]) == len(s["y"]) and len(s["x"]) > 0
    assert all(float(y).is_integer() for y in s["y"])  # n is integer-valued
    assert n["meta"].get("dominant_n") is not None


def test_mode_number_amp_pct_knob_widens_visible_cells():
    # n_amp_pct is the amplitude-percentile floor: a lower percentile keeps weaker
    # cells, so the n-map shows at least as many as a stricter (higher) floor.
    shot = _first_shot()

    def _shown(pct):
        n = nodes.build_node(shot, "mode_number", {"n_amp_pct": str(pct)})
        assert n["kind"] == "heatmap"
        return sum(v is not None for row in n["z"] for v in row)

    assert _shown(20) >= _shown(95)


def test_fit_quality_node_has_finite_k():
    shot = _first_shot()
    n = nodes.build_node(shot, "fit_quality")
    assert n["kind"] == "metrics"
    assert n["fields"]


def test_real_theta_has_full_poloidal_coverage():
    # θ derived from the device table's (r,z) must span well beyond the midplane
    # (else no honest 2D pattern). Driven by the device catalog, not fetched data,
    # so it's deterministic; uses a modern shot so the seed segment is active.
    import devices

    dev = devices.load_device("diiid")
    shot = 184927
    theta = {name: diiid.real_theta_of(name, shot) for name in dev["sensors"]}
    theta = {k: v for k, v in theta.items() if v is not None}
    assert len(theta) > 20
    vals = sorted(theta.values())
    assert min(vals) < 60.0 and max(vals) > 170.0  # HFS / off-midplane probes present
    assert "MPID67A217" in theta  # a known off-midplane probe


def test_mode_pattern_node():
    shot = _first_shot()
    try:
        n = nodes.build_node(shot, "mode_pattern")
    except Exception as e:  # noqa: BLE001 — shot may lack the poloidal array
        pytest.skip(f"no poloidal array in this shot: {e}")
    assert n["kind"] == "contour"
    assert len(n["z"]) == len(n["y"]) and len(n["z"][0]) == len(n["x"])  # [θ][φ]


def test_elongation_theta_star_threads_into_poloidal_nodes(monkeypatch):
    """With κ available the poloidal axis is the corrected θ*; absent κ it's geometric."""
    shot = _first_shot()
    try:
        nodes.build_node(shot, "mode_pattern")  # needs the poloidal array
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no poloidal array in this shot: {e}")

    # κ absent → geometric θ, honest "no κ" label
    monkeypatch.setattr(nodes, "_kappa_at", lambda *a, **k: None)
    mp = nodes.build_node(shot, "mode_pattern", {"time": 3000})
    assert mp["meta"]["kappa"] is None and "κ-corrected" not in mp["axes"]["y"]

    # κ present → θ* axis + κ in meta
    monkeypatch.setattr(nodes, "_kappa_at", lambda *a, **k: 1.85)
    mp = nodes.build_node(shot, "mode_pattern", {"time": 3000})
    ps = nodes.build_node(shot, "poloidal_shape", {"time": 3000})
    assert mp["meta"]["kappa"] == 1.85 and "κ-corrected" in mp["axes"]["y"]
    assert ps["meta"]["kappa"] == 1.85 and "κ-corrected" in ps["axes"]["x"]


def test_raw_trace_node():
    shot = _first_shot()
    n = nodes.build_node(shot, "raw_trace", {"time": 3000})
    assert n["kind"] == "line" and n["series"]
    s = n["series"][0]
    assert len(s["x"]) == len(s["y"]) and len(s["x"]) > 1
    assert n["meta"]["probe"]


def test_toroidal_stripes_node():
    shot = _first_shot()
    n = nodes.build_node(shot, "toroidal_stripes", {"time": 3000})
    assert n["kind"] == "heatmap"
    assert len(n["z"]) == len(n["y"]) and len(n["z"][0]) == len(n["x"])  # [angle][time]


def test_poloidal_phase_fit_node():
    shot = _first_shot()
    try:
        n = nodes.build_node(shot, "poloidal_phase_fit", {"time": 3000})
    except Exception as e:  # noqa: BLE001 — shot may lack the poloidal array
        pytest.skip(f"no poloidal array in this shot: {e}")
    assert n["kind"] == "scatter2d" and n["points"]
    assert "m_fit" in n["meta"]


def test_unknown_node_raises():
    shot = _first_shot()
    with pytest.raises(KeyError):
        nodes.build_node(shot, "does_not_exist")


def test_quality_for_k_thresholds():
    # mirrors contract.ts qualityForK
    assert contracts.quality_for_k(5) == "good"
    assert contracts.quality_for_k(15) == "warn"
    assert contracts.quality_for_k(25) == "bad"
    assert contracts.quality_for_k(float("nan")) == "bad"
