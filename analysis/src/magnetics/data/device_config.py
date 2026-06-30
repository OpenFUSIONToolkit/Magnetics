"""Load a device description (``data/device/<id>.json``) — the single source of
truth for a machine's sensor geometry, vessel wall, and plasma-equilibrium
pointnames.

This replaces the geometry that used to be *synthesized*: the toroidal angle that
``diiid`` parsed out of the pointname digits (exact for the Mirnov probes, but a few
degrees off on the 3D coils and flat across a poloidal column) and the cosmetic
poloidal-angle offset table. Every sensor record here carries the genuine
``r``/``z``/``phi`` (and, for the integrated-Bp probes, the turns·area ``na`` and
differencing ``pair``), so the poloidal angle is the real ``atan2(z, r − R0)`` rather
than an approximation. (The service ``_real_geometry`` table — the same positions,
auto-generated for the offline *mock* machines — is unaffected; this is the live path.)

The loader is device-agnostic: a new machine drops in as ``data/device/<id>.json``
with no code change. ``diiid`` binds the DIII-D file; the service resolves a shot's
device from its HDF5 ``device`` attribute.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import h5source


@dataclass(frozen=True)
class Sensor:
    """One sensor's static geometry, straight from the device file."""
    name: str
    phi: float | None      # toroidal angle (deg), or None if the file omits it
    theta: float           # geometric poloidal angle (deg) = atan2(z, r − R0)
    r: float | None        # major radius of the sensor centre (m)
    z: float | None        # height (m)
    tilt: float | None     # sensor normal tilt (deg)
    length: float | None   # sensor length (m)
    na: float | None       # turns · area (integrated-Bp calibration), if given
    pair: str | None       # differencing partner pointname, if given


class DeviceConfig:
    """Parsed ``data/device/<id>.json`` with cheap per-sensor lookups."""

    def __init__(self, device: str, raw: dict):
        self.device = device
        self.name = str(raw.get("name", device))
        self.R0 = float(raw.get("R0", 0.0))
        wall = raw.get("wall") or {}
        self.wall_r = np.asarray(wall.get("r", []), dtype=float)
        self.wall_z = np.asarray(wall.get("z", []), dtype=float)
        self.plasma_pointnames: dict = raw.get("plasma pointnames", {})
        self._sensors: dict[str, Sensor] = {}
        for nm, s in (raw.get("sensors") or {}).items():
            r = _maybe_float(s.get("r"))
            z = _maybe_float(s.get("z"))
            # Geometric poloidal angle about the device's geometric centre. The
            # magnetic axis sits a little above Z=0 and shifts shot-to-shot, but the
            # static layout uses the geometric centre (R0, 0) — the κ correction
            # (core.geometry.elongation_theta_star) is the shaping refinement.
            theta = (math.degrees(math.atan2(z, r - self.R0)) % 360.0
                     if r is not None and z is not None else 0.0)
            self._sensors[nm] = Sensor(
                name=nm, phi=_maybe_float(s.get("phi")), theta=theta, r=r, z=z,
                tilt=_maybe_float(s.get("tilt")), length=_maybe_float(s.get("length")),
                na=_maybe_float(s.get("na")), pair=s.get("pair"))

    def sensor(self, name: str) -> Sensor | None:
        return self._sensors.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._sensors

    def wall(self) -> tuple[np.ndarray, np.ndarray] | None:
        """(R, Z) vessel-wall polyline, or None if the file has no wall."""
        if self.wall_r.size and self.wall_z.size:
            return self.wall_r, self.wall_z
        return None


def _maybe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _device_path(device: str):
    return h5source.data_dir() / "device" / f"{device.lower()}.json"


@lru_cache(maxsize=8)
def load(device: str = "diiid") -> DeviceConfig:
    """Load and cache ``data/device/<device>.json``. Raises FileNotFoundError with
    the list of available device files if it's missing."""
    path = _device_path(device)
    if not path.exists():
        avail = ", ".join(sorted(p.stem for p in path.parent.glob("*.json"))) \
            if path.parent.exists() else "(none)"
        raise FileNotFoundError(
            f"no device file for {device!r} at {path}; available: {avail}")
    return DeviceConfig(device, json.loads(path.read_text()))
