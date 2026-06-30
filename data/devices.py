#!/usr/bin/env python3
"""Per-device config + shot-aware geometry resolution (data/device/<name>.json).

The device file is the single source of truth for a machine's mdsip servers,
sensor sets, and — since the time-segment refactor — its *shot-aware* hardware
geometry. Each sensor (and the wall) holds a ``segments`` list; a segment is
valid from its ``since_shot`` (inclusive) until the next segment's ``since_shot``,
and carries that era's geometry plus an optional ``pointname`` override.

This module is the ONE implementation of that resolution, imported by both the
fetcher (``data/toksearch_fetch.py``) and the analysis package
(``magnetics.data.diiid`` via the catalog-path shim), so fetch and analysis can
never disagree about which pointname/position a shot maps to.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DEVICE_DIR = Path(__file__).resolve().parent / "device"

# A segment whose pointname is this sentinel marks the channel decommissioned for
# that shot range: it is not fetched, and has no geometry. Case-insensitive.
NOT_AVAILABLE = "NotAvailable"


@lru_cache(maxsize=8)
def load_device(device: str) -> dict:
    """Load data/device/<device>.json (case-insensitive), or raise with the list.

    Cached: the device file is static within a process. Call ``load_device.cache_clear()``
    if it is edited at runtime.
    """
    path = DEVICE_DIR / f"{device.lower()}.json"
    if not path.exists():
        avail = ", ".join(sorted(p.stem for p in DEVICE_DIR.glob("*.json"))) or "none"
        raise ValueError(f"unknown device {device!r}; "
                         f"available in {DEVICE_DIR}: {avail}")
    with open(path) as f:
        return json.load(f)


def _segments(item: dict | None) -> list[dict]:
    """The segment list of a hardware item, tolerating a legacy flat record
    (treated as one open-ended segment) so callers work pre/post migration."""
    if not item:
        return []
    if "segments" in item:
        return sorted(item["segments"], key=lambda s: s.get("since_shot", 0))
    return [{"since_shot": 0, **item}]  # legacy flat record → always-valid segment


def segment_at(dev: dict, sensor_id: str, shot: int) -> dict | None:
    """The hardware segment active at `shot`, or None if `shot` precedes the
    earliest segment (sensor unknown for that era)."""
    active = None
    for seg in _segments(dev.get("sensors", {}).get(sensor_id)):
        if seg.get("since_shot", 0) <= shot:
            active = seg
        else:
            break  # segments are sorted ascending; no later one can match
    return active


def pointname_at(dev: dict, sensor_id: str, shot: int) -> str | None:
    """The MDS pointname to fetch for `sensor_id` at `shot`, or None when the
    sensor is out of range (pre-earliest-segment) or decommissioned (``NotAvailable``).

    Defaults to the canonical id (the dict key) when a segment gives no explicit
    ``pointname`` override — old shots that predate a rename carry the old name.
    """
    seg = segment_at(dev, sensor_id, shot)
    if seg is None:
        return None
    pt = seg.get("pointname", sensor_id)
    if pt is None or pt.lower() == NOT_AVAILABLE.lower():
        return None
    return pt


def geometry_at(dev: dict, sensor_id: str, shot: int) -> dict | None:
    """The shot-correct geometry fields (r, z, phi, tilt, ...) for `sensor_id`,
    or None if no segment is valid at `shot`. Excludes the bookkeeping keys
    (``since_shot``, ``pointname``)."""
    seg = segment_at(dev, sensor_id, shot)
    if seg is None or pointname_at(dev, sensor_id, shot) is None:
        return None  # out of range, or decommissioned (NotAvailable)
    return {k: v for k, v in seg.items() if k not in ("since_shot", "pointname")}


def valid_at(dev: dict, sensor_id: str, shot: int) -> bool:
    """True if `sensor_id` is fetchable at `shot` (has a segment, not NotAvailable)."""
    return pointname_at(dev, sensor_id, shot) is not None
