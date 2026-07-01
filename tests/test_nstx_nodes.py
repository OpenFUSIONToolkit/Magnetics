"""NSTX/NSTX-U node-builder genericization.

The service node builders must render an NSTX shot for the rotating/MODESPEC views
and the Sensors geometry view — instead of 422-ing because channel selection was
hardcoded to DIII-D pointname families. The ``nstx_shot`` fixture is a synthetic
NSTX-U shot (real ``nstx.json`` channel names, fabricated signals; see
``tests/synthetic_shot.py`` and the test-data policy in CLAUDE.md).
"""

from __future__ import annotations

import pytest

from magnetics.data import device_geom, h5source
from magnetics.service import nodes

# Rotating/MODESPEC views (+ geometry) that must resolve for an NSTX shot.
_ROTATING_NODES = ["spectrogram", "mode_number", "n_spectrum", "coherence", "phase_fit"]


def test_nstx_shot_resolves_to_nstx_device(nstx_shot):
    assert h5source.device_id(nstx_shot) == "nstx"
    assert nodes._dev_geom(nstx_shot).device_id == "nstx"


@pytest.mark.parametrize("node_id", _ROTATING_NODES + ["geometry"])
def test_nstx_node_builds(nstx_shot, node_id):
    """Each view returns a valid self-describing contract dict (no 422/ValueError)."""
    node = nodes.build_node(nstx_shot, node_id, {})
    assert isinstance(node, dict)
    assert node.get("kind")


def test_nstx_toroidal_array_selected_by_set_membership(nstx_shot):
    """The rotating n-fit array comes from an NSTX toroidal sensor set, with ≥ 4
    distinct-φ probes (so a mode number resolves)."""
    arr = nodes._toroidal_arr(nstx_shot)
    assert len(arr) >= 4
    phis = {round(p, 1) for _, p in arr}
    assert len(phis) >= 4
    # Real fastmag node paths, not DIII-D pointnames.
    assert all(n.startswith("\\") for n, _ in arr)


def test_nstx_pick_pair_toroidally_separated(nstx_shot):
    (n1, p1), (n2, p2) = nodes._pick_pair(nstx_shot)
    assert n1 != n2
    assert p1 != p2


def test_nstx_geometry_not_all_coil(nstx_shot):
    """The Sensors view must classify NSTX Mirnov probes as Bp (set membership),
    not fall through to the DIII-D 'coil' family default."""
    geo = nodes.build_node(nstx_shot, "geometry", {})
    kinds = {s["kind"] for s in geo["meta"]["sensors"]}
    assert geo["meta"]["sensors"], "no sensors with geometry at this shot"
    assert kinds != {"coil"}
    assert "Bp" in kinds


def test_nstx_device_geom_prefers_explicit_theta(nstx_shot):
    """NSTX stores authoritative φ/θ per sensor; the accessor must use the explicit
    θ (not derive it from r,z)."""
    dg = device_geom.get("nstx")
    name = "\\bdot_l1dmivvhn3_raw"  # θ = -33.47 at NSTX-U
    th = dg.real_theta_of(name, int(nstx_shot))
    assert th is not None
    # -33.47 wrapped into [0,360) → 326.53; the (r,z) derivation would differ.
    assert round(th, 1) == round(-33.47 % 360.0, 1)
