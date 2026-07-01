"""DIII-D device specifics — a thin back-compat shim over :mod:`device_geom`.

Historically this module carried the DIII-D-only mapping from a PTDATA pointname
to (φ, θ, kind, family). That logic now lives, device-agnostically, in
``device_geom.DeviceGeometry``; this module just delegates to the ``"diiid"``
instance so every existing ``diiid.*`` caller keeps working unchanged.

Geometry is **shot-aware**: positions come from the device file's time-segmented
table (``data/device/diiid.json``, resolved by ``devices`` per shot). family/kind
stay name-based (they don't change with shot).
"""

from __future__ import annotations

from .device_geom import get as _get

_DIIID = _get("diiid")


def family_of(name: str) -> str:
    return _DIIID.family_of(name)


def kind_of(name: str) -> str:
    return _DIIID.kind_of(name)


def phi_of(name: str, shot=None) -> float | None:
    return _DIIID.phi_of(name, shot)


def real_theta_of(name: str, shot) -> float | None:
    return _DIIID.real_theta_of(name, shot)


def theta_of(name: str, shot=None) -> float:
    return _DIIID.theta_of(name, shot)

def poloidal_group(name: str, shot=None) -> str | None:
    """'inboard' | 'outboard' from the sensor's REAL poloidal angle (None if unknown).

    Inboard = high-field side (θ within ±90° of 180°); outboard = low-field side
    (θ within ±90° of 0°). Uses real_theta_of, so it is only meaningful where the
    device table has physical θ (post-merge: derived from shot-correct r,z)."""
    th = real_theta_of(name, shot)
    if th is None:
        return None
    d_in = abs(((th - 180.0 + 180.0) % 360.0) - 180.0)   # angular distance to 180°
    return "inboard" if d_in < 90.0 else "outboard"

def sensor(name: str, shot=None) -> dict:
    return _DIIID.sensor(name, shot)
