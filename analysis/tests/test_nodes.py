"""Backend node-builder tests: build each GUI node from whatever fetched HDF5 is
on disk and assert it matches the contract.ts shape. Skips cleanly when no shot
files are present (e.g. CI without data).
"""
from __future__ import annotations

import pytest

from magnetics.core import contracts
from magnetics.data import h5source
from magnetics.service import nodes
from tests import synthetic_h5


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
    n = nodes.build_node(shot, "contour")
    assert n["kind"] == "contour"
    assert len(n["z"]) == len(n["y"]) and len(n["z"][0]) == len(n["x"])


def test_fit_quality_node_has_finite_k():
    shot = _first_shot()
    n = nodes.build_node(shot, "fit_quality")
    assert n["kind"] == "metrics"
    assert n["fields"]


def test_phase_fit_reads_only_cursor_window(tmp_path, monkeypatch):
    shot = 999997
    names = ["MPID66M020", "MPID66M067", "MPI66M307D", "MPI66M340D"]
    phis = [20.0, 67.0, 307.0, 340.0]
    channels, _time_ms, _ = synthetic_h5.rotating_array(
        phis, names=names, n=2, f_khz=8.0, fs_khz=500.0, dur_ms=30.0)
    synthetic_h5.write_shot(tmp_path / "phase_fit.h5", channels, shot=shot)

    monkeypatch.setenv("MAGNETICS_DATA_DIR", str(tmp_path))
    h5source.refresh()
    nodes.refresh()

    real_load_window_stack = nodes.h5source.load_window_stack
    calls = []

    def record_load_window_stack(shot_id, channel_names, tmin_ms=None,
                                 tmax_ms=None, stride=1):
        calls.append((tuple(channel_names), tmin_ms, tmax_ms, stride))
        return real_load_window_stack(shot_id, channel_names, tmin_ms, tmax_ms, stride)

    monkeypatch.setattr(nodes.h5source, "load_window_stack", record_load_window_stack)

    node = nodes.build_node(
        str(shot),
        "phase_fit",
        {"time": "10.0", "window_ms": "1.5", "f_khz": "8.0"},
    )

    assert node["kind"] == "scatter2d"
    assert calls
    _channel_names, tmin_ms, tmax_ms, stride = calls[-1]
    assert tmin_ms == 8.5
    assert tmax_ms == 11.5
    assert stride == 1


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
