"""Per-shot bad-channel exclusions (issue #56).

A misbehaving probe — dead channel, railed signal, wrong gain, disconnected
integrator — otherwise flows straight into both analyses and silently skews the
fits. This module is the one source of truth for "ignore these channels on this
shot", consulted below both analysis paths at channel selection so a single
exclusion applies everywhere rather than per view.

Scope is **per shot**, because that is how bad channels actually behave: a probe
is bad *on a shot*, not universally. Exclusions persist in one small JSON file
next to the shot data (``<data dir>/exclusions.json``), so they survive a reload
and are seen by anyone opening that shot on the same install.

Transport is separate from storage: the service reads this store and the GUI
carries the resulting names on each ``/api/node`` request as an ``exclude=``
query param. That keeps the analysis caches (all ``lru_cache`` keyed on their
arguments) correct by construction — an exclusion change is a different cache
key, so nothing stale can be served.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

from . import h5source

# One file for every shot: these are a handful of names each, and a single
# document keeps the write atomic (temp file + os.replace) without a per-shot
# file sprawl in the data dir.
_FILENAME = "exclusions.json"
_LOCK = threading.Lock()  # serialize read-modify-write across request threads


def _path():
    return h5source.data_dir() / _FILENAME


def _load_all() -> dict[str, list[str]]:
    try:
        with open(_path(), encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # Tolerate hand-edits: keep only str->list-of-str entries.
    out: dict[str, list[str]] = {}
    for shot, names in raw.items():
        if isinstance(names, list):
            out[str(shot)] = sorted({str(n) for n in names if str(n).strip()})
    return out


def get(shot: str | int) -> list[str]:
    """Channel names excluded from analysis for ``shot`` (sorted, may be empty)."""
    with _LOCK:
        return list(_load_all().get(str(shot), []))


def set_for_shot(shot: str | int, names) -> list[str]:
    """Replace the exclusion set for ``shot``. Returns the stored (sorted) list.

    An empty list drops the shot's entry entirely, so a cleared shot leaves no
    residue in the file.
    """
    cleaned = sorted({str(n).strip() for n in (names or []) if str(n).strip()})
    with _LOCK:
        all_ = _load_all()
        if cleaned:
            all_[str(shot)] = cleaned
        else:
            all_.pop(str(shot), None)
        _write(all_)
    return cleaned


def _write(all_: dict[str, list[str]]) -> None:
    """Atomically replace the store (temp file in the same dir, then rename), so
    a crash mid-write cannot leave a truncated file that loses every shot."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".exclusions-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(all_, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_param(raw) -> tuple[str, ...]:
    """Parse an ``exclude=A,B`` query param into a sorted, de-duplicated tuple.

    Returned as a *tuple* because it is threaded into ``lru_cache``-keyed
    analysis calls, which require a hashable argument; sorting makes the key
    stable regardless of the order the GUI sent.
    """
    if not raw:
        return ()
    return tuple(sorted({p.strip() for p in str(raw).split(",") if p.strip()}))
