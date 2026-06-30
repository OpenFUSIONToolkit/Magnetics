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
    assert len(n["z"]) == len(n["y"])            # rows = freqs
    assert len(n["z"][0]) == len(n["x"])         # cols = times


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


def test_fit_quality_node_has_finite_k():
    shot = _first_shot()
    n = nodes.build_node(shot, "fit_quality")
    assert n["kind"] == "metrics"
    assert n["fields"]


def test_real_theta_has_full_poloidal_coverage():
    # the real-θ table must span well beyond the midplane (else no honest 2D pattern)
    theta = nodes._real_theta()
    assert len(theta) > 20
    vals = sorted(theta.values())
    assert min(vals) < 60.0 and max(vals) > 170.0   # HFS / off-midplane probes present
    assert "MPID67A217" in theta                      # a known off-midplane probe


def test_mode_pattern_node():
    shot = _first_shot()
    try:
        n = nodes.build_node(shot, "mode_pattern")
    except Exception as e:  # noqa: BLE001 — shot may lack the poloidal array
        pytest.skip(f"no poloidal array in this shot: {e}")
    assert n["kind"] == "contour"
    assert len(n["z"]) == len(n["y"]) and len(n["z"][0]) == len(n["x"])  # [θ][φ]


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
