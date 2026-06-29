"""Builders for the self-describing result contract (the GUI ⇄ analysis seam).

Every analysis returns a `Node`: a plain dict with a `kind` discriminator that the
React GUI renders generically via `<NodeView>`. These builders mirror, field for
field, the TypeScript types in `gui/web/src/lib/contract.ts` — keep the two in
sync. No physics here, just shaping.
"""
from __future__ import annotations

from typing import Any


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop None-valued optional keys so the JSON matches the TS optionals."""
    return {k: v for k, v in d.items() if v is not None}


def contour(x, y, z, axes, *, zrange=None, overlay=None, meta=None) -> dict:
    """Filled contour of a 2-D field — the SLCONTOUR φ–θ map. z is row-major [y][x]."""
    return _clean({
        "kind": "contour", "x": x, "y": y, "z": z, "axes": axes,
        "zrange": zrange, "overlay": overlay, "meta": meta,
    })


def heatmap(x, y, z, axes, *, discrete=None, zrange=None, meta=None) -> dict:
    """Image/heatmap — the MODESPEC spectrogram. discrete ⇒ z is a mode number."""
    return _clean({
        "kind": "heatmap", "x": x, "y": y, "z": z, "axes": axes,
        "discrete": discrete, "zrange": zrange, "meta": meta,
    })


def scatter2d(points, axes, *, fit=None, meta=None) -> dict:
    """Scattered points — sensor geometry, phase-vs-angle fits."""
    return _clean({
        "kind": "scatter2d", "points": points, "axes": axes,
        "fit": fit, "meta": meta,
    })


def line(series, axes, *, meta=None) -> dict:
    """One or more 1-D traces — amplitude/phase vs time, raw signals."""
    return _clean({"kind": "line", "series": series, "axes": axes, "meta": meta})


def metrics(title, fields, *, meta=None) -> dict:
    """A scalar quality panel — condition number K, χ², channel counts."""
    return _clean({"kind": "metrics", "title": title, "fields": fields,
                   "meta": meta or {}})


def quality_for_k(k: float) -> str:
    """SLCONTOUR condition-number thresholds (warn > 10, error > 20).

    Mirrors `qualityForK` in contract.ts so the GUI's traffic-light coloring and
    the backend agree.
    """
    if not (k == k) or k > 20:  # NaN or too ill-conditioned
        return "bad"
    if k > 10:
        return "warn"
    return "good"
