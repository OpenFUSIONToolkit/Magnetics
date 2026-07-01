"""Shot-aware device geometry, resolved from ``data/device/<name>.json``.

The device file (owned by the data layer) holds, per channel, r/z/phi/tilt/length/
delta_phi, a ``{r, z}`` first-wall outline, and named ``sensor_sets`` (e.g.
"Bp LFS midplane", "C-coils") used to classify sensors as Bp / Br / coil.

Device specifics (the family/set -> sensor-kind mapping) live HERE; the GUI only
ever sees generic (r, z, phi, length, delta_phi) numbers, so the Sensors view
stays device-agnostic. A different machine ships its own ``<name>.json`` file.
"""

from __future__ import annotations

import re

from . import devices

# A loop is anything with real toroidal extent; everything else is a point probe.
_LOOP_MIN_DPHI = 5.0


def _family(channel: str) -> str:
    m = re.match(r"^[A-Za-z]+", channel)
    return m.group(0) if m else channel


def _kind(family: str) -> str:
    """Family-prefix fallback when a sensor isn't in a classifying set."""
    if family.startswith("MPI"):
        return "Bp"  # Mirnov poloidal-field probes (point)
    if family.startswith(("ISL", "ESL")):
        return "Br"  # internal/external saddle loops
    return "coil"  # I-coils, C-coils, control/error-field coils


def _kind_from_set_name(set_name: str) -> str | None:
    """Infer Bp/Br/coil from a sensor-set name (e.g. 'Bp LFS midplane',
    'C-coils'); None if unknown so members fall back to the family-prefix rule."""
    s = set_name.lower()
    if "coil" in s:
        return "coil"
    if "bp" in s:
        return "Bp"
    if "br" in s:
        return "Br"
    return None


def _kind_map_from_sets(sets: dict) -> dict[str, str]:
    """name -> kind, derived from the curated ``sensor_sets``."""
    out: dict[str, str] = {}
    for set_name, spec in (sets or {}).items():
        kind = _kind_from_set_name(set_name)
        if kind is None or not isinstance(spec, dict) or spec.get("type") != "list":
            continue
        for nm in spec.get("sensors", []):
            out.setdefault(nm, kind)  # first naming set wins
    return out


def _record(name: str, r, z, phi, tilt, length, dphi, kind: str) -> dict:
    """One flat sensor record in the shape the exporter/GUI consume."""
    return {
        "name": name,
        "family": _family(name),
        "kind": kind,
        "shape": "loop" if float(dphi) > _LOOP_MIN_DPHI else "point",
        "phi": float(phi),
        "r": float(r),
        "z": float(z),
        "length": float(length),
        "delta_phi": float(dphi),
        "tilt": float(tilt),
    }


def _resolve_set(name: str, raw: dict, seen: set[str]) -> list[str]:
    """Flatten a sensor-set to its member channel names, recursing into
    ``composite`` sets and guarding against cycles."""
    if name in seen:
        return []
    seen.add(name)
    spec = raw.get(name) or {}
    if spec.get("type") == "composite":
        out: list[str] = []
        for sub in spec.get("sets", []):
            out += _resolve_set(sub, raw, seen)
        return out
    return list(spec.get("sensors", []))  # type == "list"


def _build_sets(raw: dict) -> list[dict]:
    """Each named set as {name, kind, count, sensors} with composites flattened."""
    out = []
    for name in raw:
        names = list(dict.fromkeys(_resolve_set(name, raw, set())))  # dedup, ordered
        out.append(
            {
                "name": name,
                "kind": _kind_from_set_name(name) or "coil",
                "count": len(names),
                "sensors": names,
            }
        )
    return out


def _arrays(sensors: list[dict]) -> list[dict]:
    """One summary row per family, in first-seen order."""
    seen: dict[str, dict] = {}
    for s in sensors:
        fam = s["family"]
        if fam not in seen:
            seen[fam] = {"family": fam, "kind": s["kind"], "shape": s["shape"], "count": 0}
        seen[fam]["count"] += 1
    return list(seen.values())


def device_geometry(shot: int, name: str = "diiid") -> dict:
    """The full device geometry at `shot`: sensors (shot-correct r/z/phi), the
    first-wall outline, vacuum-vessel plates, perturbation coils, an array summary,
    and the named sensor sets. Reads the device table through the shared shot-aware
    resolvers (``devices``), so it never disagrees with the fetcher."""
    dev = devices.load_device(name)
    sets_raw = dev.get("sensor_sets", {})
    kind_by_name = _kind_map_from_sets(sets_raw)
    sensors: list[dict] = []
    for ch in dev.get("sensors", {}):
        g = devices.geometry_nearest(dev, ch, shot)
        if g is None or g.get("r") is None or g.get("z") is None or g.get("phi") is None:
            continue  # no modeled geometry for this sensor
        sensors.append(
            _record(
                ch,
                g["r"],
                g["z"],
                g["phi"],
                g.get("tilt", 0.0),
                g.get("length", 0.0),
                g.get("delta_phi", 1.0),
                kind=kind_by_name.get(ch) or _kind(_family(ch)),
            )
        )
    device = dev.get("name", name)
    fw = devices.feature_at(dev, "first_wall", shot) or {}
    vv = (devices.feature_at(dev, "vacuum_vessel", shot) or {}).get("plates", [])
    coils = [
        {k: c.get(k) for k in ("name", "count", "turns", "rz", "loops")}
        for c in (devices.feature_at(dev, "coils", shot) or {}).get("sets", [])
    ]
    return {
        "device": device,
        "sensors": sensors,
        "wall": {"r": fw.get("r", []), "z": fw.get("z", []), "label": f"{device} first wall"},
        "vacuum_vessel": vv,
        "coils": coils,
        "arrays": _arrays(sensors),
        "sensor_sets": _build_sets(sets_raw),
    }
