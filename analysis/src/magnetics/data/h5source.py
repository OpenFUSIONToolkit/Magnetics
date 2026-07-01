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
    # analysis/src/magnetics/data/h5source.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4] / "data"


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
    with h5py.File(shot_file(shot), "r") as h5:
        fetched = h5.attrs.get("channels_fetched")
        return {
            "shot": int(np.asarray(h5.attrs.get("shot", shot))),
            "device": _attr_str(h5.attrs.get("device"), "DIII-D"),
            "analysis": _attr_str(h5.attrs.get("analysis"), "both"),
            "backend": _attr_str(h5.attrs.get("backend"), "?"),
            "n_channels": len([k for k in h5.keys() if k != "_timebases"]),
            "channels": [
                c.decode() if isinstance(c, bytes) else str(c)
                for c in (fetched if fetched is not None else [])
            ],
        }


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
