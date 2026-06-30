"""DIII-D device specifics: map a PTDATA pointname to (phi, theta, kind, family).

Geometry is **shot-aware**: sensors get moved a little between campaigns, so the
positions come from the device file's time-segmented table (``data/device/diiid.json``,
resolved by ``devices`` per shot) rather than being fixed. The toroidal angle phi is
the table's value; the poloidal angle theta is derived from the table's shot-correct
(r, z) about the machine axis. When a shot or sensor has no table entry (e.g. a
pre-152472 shot, or an unmodeled coil) we fall back to the old behaviour — phi parsed
from the channel name, theta an approximate per-array offset — so callers never crash.

family/kind stay name-based: they don't change with shot.
"""
from __future__ import annotations

import math
import re

from . import h5source

h5source._ensure_catalog_on_path()
import magnetics_signals as ms  # noqa: E402  (repo-root data/ catalog)
import devices  # noqa: E402   (repo-root data/ shared device resolver)

_DEVICE = "diiid"
_Z0 = 0.0  # DIII-D magnetic-axis height — origin for the poloidal angle

# family -> sensor kind (matches the contract's Bp|Br|coil vocabulary)
_KIND = {
    "MPID": "Bp", "MPI_BDOT": "Bp", "MPIF": "Bp",
    "ISLD": "Br", "ISLF": "Br", "ESLD": "Br",
    "COILS": "coil", "AUX": "aux",
}

# Approximate poloidal offset (deg) per array-id, so different poloidal rows
# separate visually. Only a FALLBACK now (used when the device table lacks r/z).
_THETA_BY_ARRAY = {"66": 0.0, "67": 15.0, "79": -15.0,
                   "1": 40.0, "2": 80.0, "3": 120.0, "4": 160.0, "5": 200.0}


def _reverse_family() -> dict[str, str]:
    rev = {}
    for fam, names in ms.GROUPS.items():
        for nm in names:
            rev[nm] = fam
    return rev


_FAMILY = _reverse_family()


def family_of(name: str) -> str:
    return _FAMILY.get(name, "?")


def kind_of(name: str) -> str:
    return _KIND.get(family_of(name), "other")


# ── device-table geometry (shot-aware) ───────────────────────────────────────
def _dev() -> dict | None:
    """The DIII-D device config, or None if unavailable (keeps the name-parse
    fallback working in environments without the device file)."""
    try:
        return devices.load_device(_DEVICE)
    except Exception:  # pragma: no cover - missing/broken device file
        return None


def _shot_int(shot) -> int | None:
    try:
        return int(shot)
    except (TypeError, ValueError):
        return None


def _geom(name: str, shot) -> dict | None:
    """Shot-correct geometry dict for `name`, or None when there's no shot, no
    device file, or the sensor isn't valid at that shot."""
    si = _shot_int(shot)
    dev = _dev()
    if si is None or dev is None:
        return None
    return devices.geometry_at(dev, name, si)


def phi_of(name: str, shot=None) -> float | None:
    """Toroidal angle (deg) at `shot` from the device table, falling back to the
    trailing digit run of the pointname (tolerating a trailing letter like the
    bdot 'D'). None if absent (e.g. 'ip', 'bt')."""
    g = _geom(name, shot)
    if g is not None and g.get("phi") is not None:
        return float(g["phi"])
    m = re.search(r"(\d+)\D*$", name)
    return float(int(m.group(1)) % 360) if m else None


def real_theta_of(name: str, shot) -> float | None:
    """Physical poloidal angle (deg) from the device table's shot-correct (r, z)
    about the machine axis (R0, Z0), or None when (r, z) isn't available. This is
    what lets callers select 'probes that have a genuine θ'."""
    g = _geom(name, shot)
    if not g or g.get("r") is None or g.get("z") is None:
        return None
    dev = _dev()
    r0 = float(dev.get("R0", 1.69)) if dev else 1.69
    return math.degrees(math.atan2(float(g["z"]) - _Z0, float(g["r"]) - r0)) % 360.0


def theta_of(name: str, shot=None) -> float:
    """Poloidal angle (deg). Real (derived from the table's r,z) when available,
    else an approximate per-array offset so the φ–θ map stays legible."""
    th = real_theta_of(name, shot)
    if th is not None:
        return th
    # cosmetic fallback (no r/z for this sensor/shot)
    fam = family_of(name)
    if fam == "COILS":
        if name.startswith(("IU", "PCIU")):
            return 60.0
        if name.startswith(("IL", "PCIL")):
            return -60.0
        return 0.0  # C-coils / RLC
    # array id = leading digits after the alpha prefix (MPID66M.. -> 66)
    m = re.match(r"[A-Za-z]+(\d+)", name)
    base = _THETA_BY_ARRAY.get(m.group(1), 0.0) if m else 0.0
    # nudge B-section probes so A/B rows don't overlap exactly
    sec = re.search(r"\d+([AB])", name)
    return base + (8.0 if sec and sec.group(1) == "B" else 0.0)


def sensor(name: str, shot=None) -> dict:
    """Full geometry record for one channel at `shot` — shot-correct (r, z, φ, θ)
    from the device table plus name-derived kind/family. r/z are None for a channel
    with no table geometry at this shot (φ then name-parsed, θ the cosmetic fallback)."""
    g = _geom(name, shot)
    return {
        "name": name,
        "phi": phi_of(name, shot),
        "theta": theta_of(name, shot),
        "r": float(g["r"]) if g and g.get("r") is not None else None,
        "z": float(g["z"]) if g and g.get("z") is not None else None,
        "kind": kind_of(name),
        "family": family_of(name),
    }
