"""DIII-D device specifics: map a PTDATA pointname to (phi, theta, kind, family).

Geometry comes from the device description (``data/device/diiid.json`` via
``device_config``): every sensor's real ``phi`` and its poloidal angle
``theta = atan2(z, r − R0)``. This replaces what this module used to *synthesize* —
a toroidal angle parsed from the pointname digits (a few degrees off on the 3D
coils, and flat across a poloidal column) and a cosmetic per-array ``theta``
offset that was never physical. Pointnames absent from the device file (e.g. the
equilibrium scalars ``ip``/``bt``/``kappa``) fall back to digit-parsing for ``phi``
and carry no poloidal angle.

``family``/``kind`` still come from the signal catalog (``magnetics_signals``),
which groups pointnames by probe family.
"""
from __future__ import annotations

import re

from . import device_config, h5source

h5source._ensure_catalog_on_path()
import magnetics_signals as ms  # noqa: E402  (repo-root data/ catalog)

_DEVICE = "diiid"

# family -> sensor kind (matches the contract's Bp|Br|coil vocabulary)
_KIND = {
    "MPID": "Bp", "MPI_BDOT": "Bp", "MPIF": "Bp",
    "ISLD": "Br", "ISLF": "Br", "ESLD": "Br",
    "COILS": "coil", "AUX": "aux",
}


def _config() -> device_config.DeviceConfig:
    return device_config.load(_DEVICE)


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
    """Toroidal angle in degrees. The real value from the device file when the
    sensor is known; otherwise parsed from the trailing digit run of the pointname
    (tolerating a trailing letter like the bdot 'D'). None if absent (e.g. 'ip')."""
    s = _config().sensor(name)
    if s is not None and s.phi is not None:
        return float(s.phi % 360.0)
    m = re.search(r"(\d+)\D*$", name)
    if not m:
        return None
    return float(int(m.group(1)) % 360)


def theta_of(name: str) -> float:
    """Geometric poloidal angle (deg) from the device file: atan2(z, r − R0).
    0.0 for pointnames with no geometry record (the midplane reference)."""
    s = _config().sensor(name)
    return float(s.theta) if s is not None else 0.0


def has_geometry(name: str) -> bool:
    """True if the device file carries a real (r, z) record for this pointname —
    i.e. ``theta_of`` is a measured angle and not the 0.0 placeholder."""
    return _config().sensor(name) is not None


def sensor(name: str) -> dict:
    """Full geometry record for one channel."""
    return {
        "name": name,
        "phi": phi_of(name),
        "theta": theta_of(name),
        "kind": kind_of(name),
        "family": family_of(name),
    }
