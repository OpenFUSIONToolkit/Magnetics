"""Device-aware sensor naming + shot-aware geometry (family/kind/φ/θ per channel).

Generalizes the old DIII-D-only ``diiid`` module so the service node builders can
render *any* device that ships a ``data/device/<id>.json`` file. One
:class:`DeviceGeometry` instance answers, for a channel name at a shot:

  * ``family_of`` / ``kind_of`` — a Bp|Br|coil classification (DIII-D from the
    pointname-family catalog; other devices from ``sensor_sets`` membership);
  * ``phi_of`` / ``real_theta_of`` / ``theta_of`` — the toroidal/poloidal angles,
    read from the device table's shot-correct segment. When the table carries an
    explicit ``theta`` (NSTX does), that authoritative value is preferred over the
    (r, z) derivation used for DIII-D.

``diiid.py`` is a thin back-compat shim over ``DeviceGeometry("diiid")`` so every
existing ``diiid.*`` caller keeps working unchanged.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from . import devices
from . import signals as ms

# family -> sensor kind (the contract's Bp|Br|coil vocabulary). DIII-D families.
_DIIID_KIND = {
    "MPID": "Bp",
    "MPI_BDOT": "Bp",
    "MPIF": "Bp",
    "ISLD": "Br",
    "ISLF": "Br",
    "ESLD": "Br",
    "COILS": "coil",
    "AUX": "aux",
}

# Approximate poloidal offset (deg) per DIII-D array-id, a FALLBACK used only when
# the device table lacks r/z and there's no explicit θ.
_THETA_BY_ARRAY = {
    "66": 0.0,
    "67": 15.0,
    "79": -15.0,
    "1": 40.0,
    "2": 80.0,
    "3": 120.0,
    "4": 160.0,
    "5": 200.0,
}


def _shot_int(shot) -> int | None:
    try:
        return int(shot)
    except TypeError, ValueError:
        return None


class DeviceGeometry:
    """Naming + shot-aware geometry accessor for one device config id."""

    def __init__(self, device_id: str = "diiid"):
        self.device_id = device_id

    # ── device file (None keeps the name-parse fallback working) ─────────────
    def _dev(self) -> dict | None:
        try:
            return devices.load_device(self.device_id)
        except Exception:  # pragma: no cover - missing/broken device file
            return None

    # ── family / kind classification ─────────────────────────────────────────
    @property
    def _is_diiid(self) -> bool:
        return self.device_id == "diiid"

    def _family_map(self) -> dict[str, str]:
        """name -> family. DIII-D uses the pointname catalog; other devices use
        the sensor-set the channel appears in (its set name)."""
        if self._is_diiid:
            return _diiid_family_map()
        return _set_family_map(self.device_id)

    def family_of(self, name: str) -> str:
        return self._family_map().get(name, "?")

    def kind_of(self, name: str) -> str:
        if self._is_diiid:
            return _DIIID_KIND.get(self.family_of(name), "other")
        # Non-DIII-D: classify from the sensor-set name the channel belongs to.
        return _set_kind_map(self.device_id).get(name, "other")

    # ── shot-aware geometry from the device table ────────────────────────────
    def _geom(self, name: str, shot) -> dict | None:
        si = _shot_int(shot)
        dev = self._dev()
        if si is None or dev is None:
            return None
        return devices.geometry_at(dev, name, si)

    def phi_of(self, name: str, shot=None) -> float | None:
        """Toroidal angle (deg) at `shot` from the device table, falling back to
        the trailing digit run of the pointname. None if absent (e.g. 'ip')."""
        g = self._geom(name, shot)
        if g is not None and g.get("phi") is not None:
            return float(g["phi"])
        m = re.search(r"(\d+)\D*$", name)
        return float(int(m.group(1)) % 360) if m else None

    def real_theta_of(self, name: str, shot) -> float | None:
        """Physical poloidal angle (deg). Prefers an explicit ``theta`` in the
        device table (NSTX stores authoritative φ/θ per sensor); otherwise derived
        from the shot-correct (r, z) about the machine axis (DIII-D). None when
        neither is available."""
        g = self._geom(name, shot)
        if not g:
            return None
        if g.get("theta") is not None:
            return float(g["theta"]) % 360.0
        if g.get("r") is None or g.get("z") is None:
            return None
        dev = self._dev()
        r0 = float(dev.get("R0", 1.69)) if dev else 1.69
        return math.degrees(math.atan2(float(g["z"]), float(g["r"]) - r0)) % 360.0

    def theta_of(self, name: str, shot=None) -> float:
        """Poloidal angle (deg). Real (explicit θ or derived from r,z) when
        available, else an approximate per-array offset so the φ–θ map stays
        legible (DIII-D cosmetic fallback)."""
        th = self.real_theta_of(name, shot)
        if th is not None:
            return th
        # cosmetic fallback (no r/z/θ for this sensor/shot) — DIII-D flavored.
        fam = self.family_of(name)
        if fam == "COILS":
            if name.startswith(("IU", "PCIU")):
                return 60.0
            if name.startswith(("IL", "PCIL")):
                return -60.0
            return 0.0  # C-coils / RLC
        m = re.match(r"[A-Za-z]+(\d+)", name)
        base = _THETA_BY_ARRAY.get(m.group(1), 0.0) if m else 0.0
        sec = re.search(r"\d+([AB])", name)
        return base + (8.0 if sec and sec.group(1) == "B" else 0.0)

    def sensor(self, name: str, shot=None) -> dict:
        """Full geometry record for one channel at `shot`."""
        g = self._geom(name, shot)
        return {
            "name": name,
            "phi": self.phi_of(name, shot),
            "theta": self.theta_of(name, shot),
            "r": float(g["r"]) if g and g.get("r") is not None else None,
            "z": float(g["z"]) if g and g.get("z") is not None else None,
            "kind": self.kind_of(name),
            "family": self.family_of(name),
        }

    def sensor_sets(self) -> dict:
        """The device's raw ``sensor_sets`` mapping ({} when unavailable)."""
        dev = self._dev()
        return (dev.get("sensor_sets") or {}) if dev else {}

    def sensor_set_members(self, set_name: str) -> list[str]:
        """The (flattened) channel ids of a named ``sensor_sets`` entry, or []
        when the device has no such set."""
        dev = self._dev()
        if dev is None:
            return []
        try:
            from .fetch.toksearch import resolve_sensor_set

            return resolve_sensor_set(dev, set_name)
        except ValueError:
            return []


@lru_cache(maxsize=8)
def get(device_id: str = "diiid") -> DeviceGeometry:
    """Cached :class:`DeviceGeometry` for a device id."""
    return DeviceGeometry(device_id)


# ── family/kind maps (cached; keyed on device id) ────────────────────────────
@lru_cache(maxsize=1)
def _diiid_family_map() -> dict[str, str]:
    """DIII-D name -> family from the pointname GROUPS catalog."""
    rev: dict[str, str] = {}
    for fam, names in ms.GROUPS.items():
        for nm in names:
            rev[nm] = fam
    return rev


@lru_cache(maxsize=8)
def _set_family_map(device_id: str) -> dict[str, str]:
    """Non-DIII-D name -> family = the first (non-composite) sensor-set the channel
    appears in. Lets callers select a toroidal/poloidal array by set membership."""
    try:
        dev = devices.load_device(device_id)
    except Exception:  # pragma: no cover
        return {}
    out: dict[str, str] = {}
    for set_name, spec in (dev.get("sensor_sets") or {}).items():
        if not isinstance(spec, dict) or spec.get("type") != "list":
            continue
        for nm in spec.get("sensors", []):
            out.setdefault(nm, set_name)  # first list-set wins
    return out


def _kind_from_set_name(set_name: str) -> str:
    """Bp|Br|coil from a sensor-set name (e.g. 'HN toroidal array', 'C-coils')."""
    s = set_name.lower()
    if "coil" in s:
        return "coil"
    if "br" in s or "saddle" in s:
        return "Br"
    # Mirnov arrays (HF/HN toroidal/poloidal, Bp midplane, …) measure Bp.
    return "Bp"


@lru_cache(maxsize=8)
def _set_kind_map(device_id: str) -> dict[str, str]:
    """Non-DIII-D name -> Bp|Br|coil, derived from the sensor-set it belongs to."""
    return {nm: _kind_from_set_name(sn) for nm, sn in _set_family_map(device_id).items()}
