"""Quasi-stationary pipeline end-to-end, against the synthetic shot.

Spans qs_io_data → qs_device.sensor_geometry → qs_prep → qs_fit → qs_bridge → contracts
— the full SLCONTOUR path. This is the coverage that was missing when the
segmented-schema geometry bug shipped: the geometry resolved to all-NaN, the fit's
SVD never converged, but the only test touching the pipeline (`_fit_quality`)
swallowed the exception. These tests assert the pipeline produces *finite* output.
"""

from __future__ import annotations

import numpy as np
import pytest

from magnetics.service import nodes


def _all_finite_grid(node):
    z = np.asarray(node["z"], dtype=float)
    return np.all(np.isfinite(z))


def test_qs_fit_returns_a_finite_contour(synthetic_shot):
    node = nodes.build_node(synthetic_shot, "qs_fit")
    assert node["kind"] == "contour"
    assert _all_finite_grid(node), "qs_fit contour has non-finite cells (NaN geometry?)"


@pytest.mark.parametrize("node_id", ["phi_t", "chi_sq_t", "amplitude", "phase_t"])
def test_qs_timeseries_are_finite(synthetic_shot, node_id):
    node = nodes.build_node(synthetic_shot, node_id)
    assert node["kind"] in ("contour", "line")
    if node["kind"] == "line":
        for s in node["series"]:
            assert np.all(np.isfinite(np.asarray(s["y"], dtype=float)))
    else:
        assert _all_finite_grid(node)


def test_sensor_geometry_extents_finite_for_synthetic_shot(synthetic_shot):
    """The direct regression guard: the QS geometry must not be NaN. Reverting
    omfit_compat.sensor_geometry to the flat `sensors[c]["r"]` read makes every
    extent NaN and this fails (as the fit's SVD then does)."""
    from magnetics.core import qs_device as oc

    geo = oc.sensor_geometry("DIII-D", shot=int(synthetic_shot))
    for coord in ("r_end1", "z_end1", "phi_end1", "theta_end1"):
        vals = np.asarray(geo[coord].values, dtype=float)
        assert np.all(np.isfinite(vals)), f"{coord} has NaNs"


def test_fit_quality_reports_a_real_fit_not_the_fallback(synthetic_shot):
    """With a QS-capable shot, fit_quality returns the real fit metrics (χ² field),
    not the geometry-only fallback — proving the pipeline ran, not just survived."""
    node = nodes.build_node(synthetic_shot, "fit_quality")
    labels = {f["label"] for f in node["fields"]}
    assert any("χ²" in lab or "chi" in lab.lower() for lab in labels), labels
