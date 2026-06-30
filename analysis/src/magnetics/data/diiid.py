"""DIII-D device specifics: map a PTDATA pointname to (phi, theta, kind, family).

The toroidal angle phi is encoded in the channel name (e.g. MPID66M**307** → 307°),
which we parse. The poloidal angle theta has no table committed to the repo yet, so
we assign an APPROXIMATE per-array offset purely so the φ–θ wall map is legible —
this is flagged in the geometry node's meta and is the obvious thing to replace
when a real geometry table lands (owner: Data Streamers, per docs/CONTRACT.md).
"""
from __future__ import annotations

import re

from . import h5source

h5source._ensure_catalog_on_path()
import magnetics_signals as ms  # noqa: E402  (repo-root data/ catalog)

# family -> sensor kind (matches the contract's Bp|Br|coil vocabulary)
_KIND = {
    "MPID": "Bp", "MPI_BDOT": "Bp", "MPIF": "Bp",
    "ISLD": "Br", "ISLF": "Br", "ESLD": "Br",
    "COILS": "coil", "AUX": "aux",
}

# Approximate poloidal offset (deg) per array-id, so different poloidal rows
# separate visually. NOT physical calibration — replace with a real table.
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


def phi_of(name: str) -> float | None:
    """Toroidal angle in degrees, parsed from the trailing digit run of the
    pointname (tolerating a trailing letter like the bdot 'D'). None if absent
    (e.g. 'ip', 'bt')."""
    m = re.search(r"(\d+)\D*$", name)
    if not m:
        return None
    return float(int(m.group(1)) % 360)


def theta_of(name: str) -> float:
    """Approximate poloidal angle (deg). Cosmetic until a real table exists."""
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


def sensor(name: str) -> dict:
    """Full geometry record for one channel."""
    return {
        "name": name,
        "phi": phi_of(name),
        "theta": theta_of(name),
        "kind": kind_of(name),
        "family": family_of(name),
    }
