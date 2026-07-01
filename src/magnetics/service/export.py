"""Serialize a `kind`-node (contracts.py) to a self-describing HDF5 file.

The GUI's per-plot "Download data" button hits `/api/node/{shot}/{node_id}/download`,
which rebuilds the node and hands it here. One writer covers every kind: the arrays
behind the plot become datasets, and the node's descriptive fields (kind, title, axis
labels, the params that produced it) become root attrs — so a downloaded file is
readable on its own, without the GUI.

Kept out of the service routes (CLAUDE.md: no physics/shaping in routes) and out of
`nodes.py` (which builds nodes) so the node→file mapping lives in exactly one place.
"""

from __future__ import annotations

import io
import json
import tempfile
from datetime import datetime, timezone
from typing import Any

import h5py
import numpy as np


def _num_array(values) -> np.ndarray:
    """Coerce a JSON list (possibly ragged / containing None) to a float array.

    Node payloads are plain JSON, so a "column" can be a list of lists (2-D fields),
    a list of numbers, or carry `null` (wrap breaks in fit lines). None → NaN keeps
    the array numeric and rectangular-friendly. A ragged/non-numeric list falls back
    to object dtype — h5py can't store that, so the caller (the /download route)
    turns the resulting write error into a clean 500 rather than a raw stack trace.
    """
    arr = np.asarray(values, dtype=object)

    def _f(x):
        return np.nan if x is None else x

    try:
        return np.asarray(np.vectorize(_f, otypes=[float])(arr), dtype=float)
    except ValueError, TypeError:
        return arr  # ragged / non-numeric — let h5py store what it can


def _write_axes(group, axes: dict | None) -> None:
    """Write axis labels (x/y/z) as attrs on `group` when present."""
    if not axes:
        return
    for key in ("x", "y", "z"):
        if axes.get(key) is not None:
            group.attrs[f"axis_{key}"] = str(axes[key])


def _write_node(h5, node: dict) -> None:
    """Write a node's arrays into the open HDF5 file `h5`, keyed by kind.

    Unknown kinds fall through to a generic dump so a node type added to the contract
    still exports its arrays without a code change here.
    """
    kind = node.get("kind")
    _write_axes(h5, node.get("axes"))

    if kind in ("contour", "heatmap"):
        h5.create_dataset("x", data=_num_array(node["x"]))
        h5.create_dataset("y", data=_num_array(node["y"]))
        h5.create_dataset("z", data=_num_array(node["z"]))
        if node.get("zrange") is not None:
            h5.attrs["zrange"] = _num_array(node["zrange"])

    elif kind == "scatter2d":
        pts = node.get("points", [])
        h5.create_dataset("x", data=_num_array([p.get("x") for p in pts]))
        h5.create_dataset("y", data=_num_array([p.get("y") for p in pts]))
        # utf-8 vlen strings, not fixed-width ASCII ("S"): sensor labels can carry
        # φ/θ/µ and a non-ASCII char would raise UnicodeEncodeError under "S".
        labels = [str(p.get("label") or "") for p in pts]
        if any(labels):
            h5.create_dataset("label", data=labels, dtype=h5py.string_dtype())
        groups = [str(p.get("group") or "") for p in pts]
        if any(groups):
            h5.create_dataset("group", data=groups, dtype=h5py.string_dtype())
        for err in ("error_x", "error_y"):
            if any(p.get(err) is not None for p in pts):
                h5.create_dataset(err, data=_num_array([p.get(err) for p in pts]))
        fit = node.get("fit")
        if fit:
            g = h5.create_group("fit")
            g.create_dataset("x", data=_num_array(fit.get("x")))
            g.create_dataset("y", data=_num_array(fit.get("y")))

    elif kind == "line":
        # one subgroup per trace; names may collide/be empty, so index them.
        for i, s in enumerate(node.get("series", [])):
            g = h5.create_group(f"series_{i}")
            g.attrs["name"] = str(s.get("name") or f"series_{i}")
            g.create_dataset("x", data=_num_array(s.get("x")))
            g.create_dataset("y", data=_num_array(s.get("y")))
            for band in ("lower", "upper"):
                if s.get(band) is not None:
                    g.create_dataset(band, data=_num_array(s[band]))
            markers = s.get("markers")
            if markers:
                mg = g.create_group("markers")
                mg.create_dataset("x", data=_num_array(markers.get("x")))
                mg.create_dataset("y", data=_num_array(markers.get("y")))

    elif kind == "equilibrium":
        h5.create_dataset("r", data=_num_array(node["r"]))
        h5.create_dataset("z", data=_num_array(node["z"]))
        h5.create_dataset("psi_n", data=_num_array(node["psi_n"]))
        b = h5.create_group("boundary")
        b.create_dataset("r", data=_num_array(node["boundary"]["r"]))
        b.create_dataset("z", data=_num_array(node["boundary"]["z"]))
        h5.attrs["axis_r"] = float(node["axis"]["r"])
        h5.attrs["axis_z"] = float(node["axis"]["z"])

    elif kind == "metrics":
        # scalars: store each field's raw value as an attr (string or number).
        for f in node.get("fields", []):
            label = str(f.get("label") or "")
            val = f.get("value")
            h5.attrs[f"field_{label}"] = val if isinstance(val, (int, float)) else str(val)

    else:
        # Unknown kind: dump every array-like value at the top level so nothing is lost.
        for key, val in node.items():
            if isinstance(val, list):
                h5.create_dataset(key, data=_num_array(val))


def node_to_hdf5(shot: str, node_id: str, node: dict, params: dict | None = None) -> bytes:
    """Serialize one `kind`-node to HDF5 bytes, with self-describing root attrs.

    `params` are the query params that produced the node (time cursor, fmin/fmax, …)
    so a download matches — and documents — exactly what was on screen.
    """

    def _fill(h5) -> None:
        h5.attrs["kind"] = str(node.get("kind", ""))
        h5.attrs["shot"] = str(shot)
        h5.attrs["node_id"] = str(node_id)
        if node.get("title"):
            h5.attrs["title"] = str(node["title"])
        h5.attrs["params"] = json.dumps(params or {}, sort_keys=True)
        h5.attrs["generated"] = datetime.now(timezone.utc).isoformat()
        h5.attrs["source"] = "magnetics service /api/node download"
        _write_node(h5, node)

    # Prefer an in-memory file (no disk touch); fall back to a temp file if this h5py
    # build lacks the file-like (fileobj) driver.
    try:
        buf = io.BytesIO()
        with h5py.File(buf, "w") as h5:
            _fill(h5)
        return buf.getvalue()
    except ValueError, OSError:
        with tempfile.NamedTemporaryFile(suffix=".h5") as tmp:
            with h5py.File(tmp.name, "w") as h5:
                _fill(h5)
            tmp.seek(0)
            return tmp.read()


# Re-export for callers that want to type the payload.
Node = dict[str, Any]
