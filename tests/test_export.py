"""HDF5 export: the node→file serializer + the /download route.

Confirms every real builder serializes without error against the synthetic shot,
that the file is valid HDF5 carrying the view params, and the per-kind dataset
layout. No real data, no network (session synthetic shots from conftest).
"""

from __future__ import annotations

import io
import json

import h5py
import pytest
from fastapi.testclient import TestClient

from magnetics.service import export, nodes
from magnetics.service.app import app

client = TestClient(app)


# ── serializer unit tests (no shot needed) ────────────────────────────────────
def test_line_node_roundtrips_series_bands_and_markers():
    node = {
        "kind": "line",
        "title": "amp",
        "axes": {"x": "t (ms)", "y": "A"},
        "series": [
            {
                "name": "n=1",
                "x": [0, 1, 2],
                "y": [1.0, 2.0, 3.0],
                "lower": [0.5, 1.5, 2.5],
                "upper": [1.5, 2.5, 3.5],
                "markers": {"x": [0, 2], "y": [1, 3]},
            }
        ],
    }
    with h5py.File(
        io.BytesIO(export.node_to_hdf5("990000", "amplitude", node, {"ns": "1,2,3"})), "r"
    ) as h:
        assert h.attrs["kind"] == "line"
        assert json.loads(h.attrs["params"]) == {"ns": "1,2,3"}
        assert h.attrs["axis_y"] == "A"
        assert list(h["series_0/y"][:]) == [1.0, 2.0, 3.0]
        assert list(h["series_0/upper"][:]) == [1.5, 2.5, 3.5]
        assert list(h["series_0/markers/x"][:]) == [0.0, 2.0]


def test_scatter2d_node_keeps_labels_and_nan_wrap_breaks():
    node = {
        "kind": "scatter2d",
        "axes": {"x": "θ", "y": "phase"},
        "points": [
            {"x": 0, "y": 1, "label": "MPI1", "group": "A", "error_y": 0.1},
            {"x": 90, "y": 2},
        ],
        "fit": {"x": [0, None, 90], "y": [1, None, 2]},
    }
    with h5py.File(io.BytesIO(export.node_to_hdf5("990000", "phase_fit", node, {})), "r") as h:
        assert list(h["x"][:]) == [0.0, 90.0]
        assert [s.decode() for s in h["label"][:]] == ["MPI1", ""]
        # error_y aligns 1:1 with points — the point without one reads NaN
        err = h["error_y"][:]
        assert err[0] == pytest.approx(0.1) and err[1] != err[1]  # NaN
        # a `null` wrap-break survives as NaN so the fit line stays plottable
        fit_x = h["fit/x"][:]
        assert fit_x[0] == 0.0 and fit_x[2] == 90.0 and fit_x[1] != fit_x[1]  # NaN


def test_scatter2d_non_ascii_labels_roundtrip():
    # φ/θ-decorated sensor labels must survive — fixed-width "S" would raise
    # UnicodeEncodeError; utf-8 vlen strings keep them.
    node = {
        "kind": "scatter2d",
        "points": [
            {"x": 0, "y": 1, "label": "Bpφ", "group": "θ-array"},
            {"x": 90, "y": 2, "label": "µ-coil", "group": "θ-array"},
        ],
    }
    with h5py.File(io.BytesIO(export.node_to_hdf5("990000", "mode_pattern", node, {})), "r") as h:
        assert [s.decode() for s in h["label"][:]] == ["Bpφ", "µ-coil"]
        assert [s.decode() for s in h["group"][:]] == ["θ-array", "θ-array"]


def test_download_serializer_failure_is_clean_500(synthetic_shot, monkeypatch):
    # A node that builds fine but can't serialize must yield a clean 500, not an
    # unhandled stack trace (the writer sits outside build_node's try/except).
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(export, "node_to_hdf5", boom)
    r = client.get(f"/api/node/{synthetic_shot}/spectrogram/download")
    assert r.status_code == 500
    assert "could not serialize" in r.json()["detail"]


def test_metrics_node_writes_scalar_attrs():
    node = {
        "kind": "metrics",
        "title": "fit quality",
        "axes": None,
        "fields": [{"label": "K", "value": 12.3}, {"label": "n chan", "value": "48"}],
    }
    with h5py.File(io.BytesIO(export.node_to_hdf5("990000", "fit_quality", node, {})), "r") as h:
        assert h.attrs["field_K"] == pytest.approx(12.3)
        assert h.attrs["field_n chan"] == "48"


def test_unknown_kind_falls_back_to_dumping_arrays():
    node = {"kind": "brand_new", "axes": {"x": "a", "y": "b"}, "vals": [1, 2, 3], "scalar": 4}
    with h5py.File(io.BytesIO(export.node_to_hdf5("1", "x", node, {})), "r") as h:
        assert list(h["vals"][:]) == [1.0, 2.0, 3.0]
        assert "scalar" not in h  # non-list values are skipped, not crashed on


# ── route tests against the synthetic shot ─────────────────────────────────────
@pytest.mark.parametrize("node_id", sorted(nodes._BUILDERS))
def test_every_builder_downloads_valid_hdf5(synthetic_shot, node_id):
    r = client.get(f"/api/node/{synthetic_shot}/{node_id}/download")
    assert r.status_code == 200, f"{node_id} → {r.status_code}: {r.text[:200]}"
    assert r.headers["content-type"] == "application/x-hdf5"
    assert f"shot_{synthetic_shot}_{node_id}.h5" in r.headers["content-disposition"]
    with h5py.File(io.BytesIO(r.content), "r") as h:
        assert h.attrs["node_id"] == node_id
        assert h.attrs["shot"] == synthetic_shot


def test_download_forwards_and_records_params(synthetic_shot):
    r = client.get(
        f"/api/node/{synthetic_shot}/spectrogram/download", params={"fmin": "5", "fmax": "40"}
    )
    assert r.status_code == 200
    with h5py.File(io.BytesIO(r.content), "r") as h:
        assert json.loads(h.attrs["params"]) == {"fmin": "5", "fmax": "40"}


def test_download_unknown_node_is_404(synthetic_shot):
    assert client.get(f"/api/node/{synthetic_shot}/not_a_real_node/download").status_code == 404


def test_download_qs_on_rotating_only_shot_is_422(rotating_only_shot):
    assert client.get(f"/api/node/{rotating_only_shot}/qs_fit/download").status_code == 422
