"""Read shot data from the HDF5 files written by the fetcher.

Tolerant of both layouts: the toksearch_fetch output (`_timebases/` dedup group +
hard-linked `time`, attrs `analysis`/`backend`) and the older pull_shot_h5 output
(per-channel `time`, no analysis attr). A channel is read the same way in both:
`/{name}/data` + `/{name}/time`.

The HDF5 output directory is `$MAGNETICS_DATA_DIR` or the repo's `data/` dir
relative to this file (where the fetcher writes `datafile/`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import h5py
import numpy as np


def data_dir() -> Path:
    env = os.environ.get("MAGNETICS_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    # src/magnetics/data/h5source.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / "data"


@lru_cache(maxsize=1)
def _shot_index() -> dict[str, Path]:
    """Map shot id (str) -> best HDF5 file (the one with the most channels)."""
    index: dict[str, Path] = {}
    best_count: dict[str, int] = {}
    # recursive: shots written by the fetcher land in data/datafile/, while older
    # files sit in data/ root — both should be discoverable.
    for path in sorted(data_dir().rglob("*.h5")):
        try:
            with h5py.File(path, "r") as h5:
                shot = str(int(np.asarray(h5.attrs.get("shot", 0))))
                n = len([k for k in h5.keys() if k != "_timebases"])
        except Exception:
            continue
        if shot == "0":
            continue
        if n > best_count.get(shot, -1):
            best_count[shot] = n
            index[shot] = path
    return index


def refresh() -> None:
    """Forget the cached file index (call after a new fetch writes a file)."""
    _shot_index.cache_clear()


def _shot_of(path: Path) -> str | None:
    """The shot id (str) a file belongs to, or None if it isn't a shot file."""
    try:
        with h5py.File(path, "r") as h5:
            shot = str(int(np.asarray(h5.attrs.get("shot", 0))))
    except Exception:
        return None
    return shot if shot != "0" else None


def delete_shot(shot: str | int) -> list[str]:
    """Delete EVERY HDF5 file backing `shot` from the data dir; return the paths
    removed. A shot can span more than one file (different windows/fmax, or a
    bench artifact), so we match on the stored ``shot`` attr rather than a single
    indexed path. Refreshes the index afterward. Empty list = nothing matched."""
    target = str(shot)
    removed: list[str] = []
    for path in sorted(data_dir().rglob("*.h5")):
        if _shot_of(path) == target:
            try:
                path.unlink()
                removed.append(str(path))
            except OSError:
                pass  # e.g. already gone / permission — skip, keep clearing the rest
    refresh()
    return removed


def delete_all_shots() -> list[str]:
    """Delete every shot HDF5 file in the data dir (the "clear all"); return the
    paths removed. Only files that parse as shot files (a non-zero ``shot`` attr)
    are touched, so unrelated .h5 are left alone. Refreshes the index afterward."""
    removed: list[str] = []
    for path in sorted(data_dir().rglob("*.h5")):
        if _shot_of(path) is not None:
            try:
                path.unlink()
                removed.append(str(path))
            except OSError:
                pass
    refresh()
    return removed


def shot_file(shot: str | int) -> Path:
    path = _shot_index().get(str(shot))
    if path is None:
        raise KeyError(f"no HDF5 file for shot {shot} in {data_dir()}")
    return path


def _attr_str(v, default=""):
    if v is None:
        return default
    if isinstance(v, bytes):
        return v.decode()
    return str(v)


def list_shots() -> list[dict]:
    """One MachineInfo-shaped dict per available shot file."""
    out = []
    for shot, path in sorted(_shot_index().items()):
        with h5py.File(path, "r") as h5:
            device = _attr_str(h5.attrs.get("device"), "DIII-D")
            analysis = _attr_str(h5.attrs.get("analysis"), "both")
            backend = _attr_str(h5.attrs.get("backend"), "?")
            n = len([k for k in h5.keys() if k != "_timebases"])
        out.append(
            {
                "id": shot,
                "label": f"{device} {shot}",
                "device": device,
                "note": f"{n} channels · {analysis} · {backend} · {path.name}",
                "mock": False,
            }
        )
    return out


def meta(shot: str | int) -> dict:
    from . import devices

    with h5py.File(shot_file(shot), "r") as h5:
        fetched = h5.attrs.get("channels_fetched")
        return {
            "shot": int(np.asarray(h5.attrs.get("shot", shot))),
            "device": _attr_str(h5.attrs.get("device"), "DIII-D"),
            # Prefer the stored config id; else resolve the display name -> id (a bare
            # .lower() would yield an invalid "diii-d" that load_device can't open).
            "device_id": _attr_str(h5.attrs.get("device_id"), "")
            or (devices.resolve_device_id(_attr_str(h5.attrs.get("device"), "DIII-D")) or "diiid"),
            "analysis": _attr_str(h5.attrs.get("analysis"), "both"),
            "backend": _attr_str(h5.attrs.get("backend"), "?"),
            "n_channels": len([k for k in h5.keys() if k != "_timebases"]),
            "channels": [
                c.decode() if isinstance(c, bytes) else str(c)
                for c in (fetched if fetched is not None else [])
            ],
        }


def device_id(shot: str | int) -> str:
    """The device *config id* (``nstx``/``diiid``) for a shot file. Prefers the
    ``device_id`` attr written at fetch time; falls back to resolving the display
    ``device`` name -> id (older files), defaulting to ``diiid``."""
    from . import devices

    with h5py.File(shot_file(shot), "r") as h5:
        did = h5.attrs.get("device_id")
        if did is not None:
            return _attr_str(did, "diiid")
        name = _attr_str(h5.attrs.get("device"), "DIII-D")
    return devices.resolve_device_id(name) or "diiid"


def channel_names(shot: str | int) -> list[str]:
    with h5py.File(shot_file(shot), "r") as h5:
        return [k for k in h5.keys() if k != "_timebases"]


def load_channel(shot: str | int, name: str):
    """Return (time_ms float64, data float32) for one channel."""
    with h5py.File(shot_file(shot), "r") as h5:
        if name not in h5:
            raise KeyError(f"channel {name!r} not in shot {shot}")
        g = h5[name]
        return np.asarray(g["time"][:]), np.asarray(g["data"][:])


def load_data(shot: str | int, name: str):
    """Return the data array (float32) for one channel, without reading its time.

    Callers that need only the signal (e.g. stacking many channels that share one
    clock) avoid materializing every channel's time vector — the time axis is ~2x
    the signal here, so reading it per channel is the dominant needless cost.
    """
    with h5py.File(shot_file(shot), "r") as h5:
        if name not in h5:
            raise KeyError(f"channel {name!r} not in shot {shot}")
        return np.asarray(h5[name]["data"][:])
