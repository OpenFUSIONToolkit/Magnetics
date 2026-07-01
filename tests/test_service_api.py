"""FastAPI route + error-mapping tests against the synthetic shot.

Exercises the real HTTP seam the GUI's useNode() consumes: `/api/node/...`
routing, query-param forwarding, and the KeyError→404 / ValueError→422 mapping.
Uses the session synthetic shots from conftest (no real data, no network).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from magnetics.service import nodes
from magnetics.service.app import app

client = TestClient(app)

_GRID_KINDS = {"heatmap", "contour"}
_VALID_KINDS = {"contour", "heatmap", "scatter2d", "line", "metrics", "equilibrium"}


def test_machines_lists_the_synthetic_shot(synthetic_shot):
    r = client.get("/api/machines")
    assert r.status_code == 200
    ids = {m["id"] for m in r.json()}
    assert synthetic_shot in ids
    row = next(m for m in r.json() if m["id"] == synthetic_shot)
    assert row["mock"] is False


@pytest.mark.parametrize("node_id", sorted(nodes._BUILDERS))
def test_every_builder_serves_a_valid_node(synthetic_shot, node_id):
    r = client.get(f"/api/node/{synthetic_shot}/{node_id}")
    assert r.status_code == 200, f"{node_id} → {r.status_code}: {r.text[:200]}"
    node = r.json()
    assert node["kind"] in _VALID_KINDS
    if node["kind"] in _GRID_KINDS:
        # z is [n_y][n_x] — the heatmap/contour invariant the GUI relies on.
        assert len(node["z"]) == len(node["y"])
        assert all(len(row) == len(node["x"]) for row in node["z"])


def test_unknown_node_id_is_404(synthetic_shot):
    r = client.get(f"/api/node/{synthetic_shot}/not_a_real_node")
    assert r.status_code == 404


def test_unknown_shot_is_404():
    r = client.get("/api/node/100/geometry")
    assert r.status_code == 404


def test_qs_on_rotating_only_shot_is_422(rotating_only_shot):
    # No Bp LFS midplane array in this pull → ValueError → 422 (not an opaque 500).
    r = client.get(f"/api/node/{rotating_only_shot}/qs_fit")
    assert r.status_code == 422
    assert r.json()["detail"]  # carries the reason
