"""Producer-side meta-contract tests.

The `kind`-node top-level shapes are typed on both sides, but the load-bearing
`meta` payload is untyped (`dict[str, Any]` ⇄ `Record<string, unknown>`) and the
GUI tabs read ~20 named meta fields with no validation. A rename in a builder
silently blanks or degrades a panel. These tests pin the meta fields each tab
actually consumes, on the side that produces them.
"""

from __future__ import annotations

from magnetics.service import nodes


def _meta(shot, node_id):
    return nodes.build_node(shot, node_id).get("meta", {})


def test_geometry_meta_has_scene_fields(synthetic_shot):
    # SensorsTab reads these; a rename of sensors/wall blanks the whole scene.
    meta = _meta(synthetic_shot, "geometry")
    for key in ("sensors", "wall", "sensor_sets", "vv", "coils"):
        assert key in meta, f"geometry meta missing {key!r}"


def test_signal_conditioning_meta_pairs(synthetic_shot):
    # QuasiStationaryTab builds the channel checkboxes + raw/prepared traces from these.
    pairs = _meta(synthetic_shot, "signal_conditioning").get("pairs")
    assert pairs, "signal_conditioning meta.pairs missing/empty"
    for key in ("channel", "prepared_idx", "raw_idx"):
        assert key in pairs[0], f"pairs[] missing {key!r}"


def test_amplitude_meta_fields(synthetic_shot):
    meta = _meta(synthetic_shot, "amplitude")
    assert "legend_title" in meta
    # the ±1σ band rides in the typed per-series lower/upper, not meta.sigma
    node = nodes.build_node(synthetic_shot, "amplitude")
    assert all("lower" in s and "upper" in s for s in node["series"])


def test_phase_t_meta_fields(synthetic_shot):
    meta = _meta(synthetic_shot, "phase_t")
    assert "phase_visible" in meta
    node = nodes.build_node(synthetic_shot, "phase_t")
    assert all("lower" in s and "upper" in s for s in node["series"])


def test_phase_fit_reports_n_estimate(synthetic_shot):
    assert "n_estimate" in _meta(synthetic_shot, "phase_fit")


def test_poloidal_phase_fit_reports_m_fit(synthetic_shot):
    assert "m_fit" in _meta(synthetic_shot, "poloidal_phase_fit")
