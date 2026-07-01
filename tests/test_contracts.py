"""core/contracts builders — the producer half of the kind-node contract mirrored
by gui/web/src/lib/contract.ts. Asserts each builder emits the required keys the
GUI narrows on, and that `_clean` drops None optionals (so JSON matches the TS
`?:` optionals rather than shipping nulls the GUI doesn't expect)."""

from __future__ import annotations

from magnetics.core import contracts as c

_AXES = {"x": "x", "y": "y"}


def test_contour_keys_and_optional_dropping():
    node = c.contour([0, 1], [0, 1], [[1, 2], [3, 4]], _AXES)
    assert node["kind"] == "contour"
    assert {"kind", "x", "y", "z", "axes"} <= node.keys()
    assert "zrange" not in node and "overlay" not in node  # None optionals dropped
    node2 = c.contour([0, 1], [0, 1], [[1, 2], [3, 4]], _AXES, zrange=[-1, 1])
    assert node2["zrange"] == [-1, 1]


def test_heatmap_keys():
    node = c.heatmap([0, 1], [0, 1], [[1, 2], [3, 4]], _AXES, discrete=True)
    assert node["kind"] == "heatmap"
    assert {"kind", "x", "y", "z", "axes", "discrete"} <= node.keys()


def test_scatter2d_keys():
    node = c.scatter2d([{"x": 1.0, "y": 2.0}], _AXES)
    assert node["kind"] == "scatter2d"
    assert {"kind", "points", "axes"} <= node.keys()
    assert "fit" not in node  # dropped when None


def test_line_keys():
    node = c.line([{"name": "a", "x": [0, 1], "y": [1, 2]}], _AXES)
    assert node["kind"] == "line"
    assert {"kind", "series", "axes"} <= node.keys()


def test_metrics_keys():
    node = c.metrics("Title", [{"label": "K", "value": 2.1}])
    assert node["kind"] == "metrics"
    assert {"kind", "title", "fields"} <= node.keys()


def test_equilibrium_keys_and_default_axes():
    node = c.equilibrium(
        [0, 1], [0, 1], [[0, 1], [1, 0]], {"r": [1], "z": [0]}, {"r": 1.7, "z": 0.0}
    )
    assert node["kind"] == "equilibrium"
    assert {"kind", "r", "z", "psi_n", "boundary", "axis", "axes"} <= node.keys()
    assert node["axes"]["x"] == "R (m)"  # default applied


def test_quality_for_k_thresholds():
    assert c.quality_for_k(2.0) == "good"
    assert c.quality_for_k(15.0) == "warn"
    assert c.quality_for_k(25.0) == "bad"
    assert c.quality_for_k(float("nan")) == "bad"
