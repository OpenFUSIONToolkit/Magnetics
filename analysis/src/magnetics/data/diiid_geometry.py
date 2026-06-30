<<<<<<< Updated upstream
"""DIII-D static sensor geometry, loaded from ``data/device/<name>.json``.

The device file (owned by the data layer) holds, per channel, r/z/phi/tilt/length/
delta_phi, a ``{r, z}`` first-wall outline, and named ``sensor_sets`` (e.g.
"Bp LFS midplane", "C-coils") used to classify sensors as Bp / Br / coil.

Device specifics (the family/set -> sensor-kind mapping) live HERE; the GUI only
ever sees generic (r, z, phi, length, delta_phi) numbers, so the Sensors view
stays device-agnostic. A different machine ships its own ``<name>.json`` file.
=======
"""DIII-D static sensor geometry.

Source of truth, in priority order:

  1. ``data/device/<name>.json`` — the device's canonical sensor file (owned by
     the data team's device-agnostic-sensor-sets work): a dict of sensors keyed by
     channel name with r/z/phi/tilt/length/delta_phi, a {r,z} wall outline, and
     named ``sensor_sets`` (e.g. "Bp LFS midplane") used to classify Bp/Br/coil.
  2. Bundled fallback — ``diiid_sensors.txt`` (the layout table) + ``diiid_wall.txt``
     (the &wall namelist), so this view works before that file lands on this branch.

The output shape is identical either way, so the exporter, contract, and GUI never
change: when the canonical JSON appears on the branch, the loader auto-switches to
it and the bundled fallback can be deleted.

Device specifics (family -> sensor kind, the schematic wall fallback) live HERE;
the GUI only ever sees generic (r, z, phi, length, delta_phi) numbers, so the
Sensors view stays device-agnostic.
>>>>>>> Stashed changes
"""
from __future__ import annotations

import json
import re
from pathlib import Path

<<<<<<< Updated upstream
=======
from ..core import geometry

_TABLE = Path(__file__).with_name("diiid_sensors.txt")
_WALL_FILE = Path(__file__).with_name("diiid_wall.txt")

# Fallback vessel cross-section (Miller D-shape) for devices with no wall data.
_WALL = dict(r0=1.70, a=0.75, kappa=1.85, delta=0.45)

>>>>>>> Stashed changes
# A loop is anything with real toroidal extent; everything else is a point probe.
_LOOP_MIN_DPHI = 5.0


def _device_json(name: str = "diiid") -> Path:
    """Locate ``data/device/<name>.json`` by walking up from this file."""
    rel = Path("data") / "device" / f"{name}.json"
    for parent in Path(__file__).resolve().parents:
        cand = parent / rel
        if cand.exists():
            return cand
    raise FileNotFoundError(f"device geometry file not found: {rel}")


def _family(channel: str) -> str:
    m = re.match(r"^[A-Za-z]+", channel)
    return m.group(0) if m else channel


<<<<<<< Updated upstream
def _kind(family: str) -> str:
    """Family-prefix fallback when a sensor isn't in a classifying set."""
    if family.startswith("MPI"):
        return "Bp"          # Mirnov poloidal-field probes (point)
    if family.startswith(("ISL", "ESL")):
        return "Br"          # internal/external saddle loops
    return "coil"            # I-coils, C-coils, control/error-field coils
=======
def _record(name: str, r, z, phi, tilt, length, dphi, kind: str) -> dict:
    """One flat sensor record in the shape the exporter/GUI consume."""
    return {
        "name": name,
        "family": _family(name),
        "kind": kind,
        "shape": "loop" if float(dphi) > _LOOP_MIN_DPHI else "point",
        "phi": float(phi), "r": float(r), "z": float(z),
        "length": float(length), "delta_phi": float(dphi), "tilt": float(tilt),
    }


# ── canonical source: data/device/<name>.json ────────────────────────────────
def _device_json(name: str = "diiid") -> Path | None:
    """Find ``data/device/<name>.json`` by walking up from this file. Returns None
    until that file exists on the branch (then the loader prefers it)."""
    rel = Path("data") / "device" / f"{name}.json"
    for parent in Path(__file__).resolve().parents:
        cand = parent / rel
        if cand.exists():
            return cand
    return None


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
        if not isinstance(spec, dict) or spec.get("type") != "list":
            continue
        kind = _kind_from_set_name(set_name)
        if kind is None:
            continue
        for nm in spec.get("sensors", []):
            out.setdefault(nm, kind)  # first naming set wins
    return out


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
        out.append({"name": name, "kind": _kind_from_set_name(name) or "coil",
                    "count": len(names), "sensors": names})
    return out


def _from_json(doc: dict) -> dict:
    sets_raw = doc.get("sensor_sets", {})
    kind_by_name = _kind_map_from_sets(sets_raw)
    sensors: list[dict] = []
    for name, v in doc.get("sensors", {}).items():
        try:
            sensors.append(_record(
                name, v["r"], v["z"], v["phi"], v.get("tilt", 0.0),
                v.get("length", 0.0), v.get("delta_phi", 1.0),
                kind=kind_by_name.get(name) or _kind(_family(name))))
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed rows
    wall = doc.get("wall") or {}
    if wall.get("r") and wall.get("z"):
        wall_node = {"r": wall["r"], "z": wall["z"],
                     "label": f"{doc.get('name', 'device')} first wall"}
    else:
        wall_node = _fallback_wall()
    return {"device": doc.get("name", "device"), "sensors": sensors,
            "wall": wall_node, "arrays": _arrays(sensors),
            "sensor_sets": _build_sets(sets_raw)}


# ── bundled fallback: diiid_sensors.txt + diiid_wall.txt ──────────────────────
def _parse_namelist_array(text: str) -> list[float]:
    """Parse a Fortran-namelist numeric array, honouring ``N*value`` repeats."""
    vals: list[float] = []
    for tok in text.replace(",", " ").split():
        if tok in ("/", "&end", "&END"):
            break
        try:
            if "*" in tok:
                n, val = tok.split("*")
                vals += [float(val)] * int(n)
            else:
                vals.append(float(tok))
        except ValueError:
            break
    return vals
>>>>>>> Stashed changes


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


<<<<<<< Updated upstream
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
        "phi": float(phi), "r": float(r), "z": float(z),
        "length": float(length), "delta_phi": float(dphi), "tilt": float(tilt),
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
        out.append({"name": name, "kind": _kind_from_set_name(name) or "coil",
                    "count": len(names), "sensors": names})
    return out
=======
def _fallback_wall() -> dict:
    wall = _real_wall()
    if wall is not None:
        r, z = wall
        return {"r": r, "z": z, "label": "DIII-D first wall"}
    rs, zs = geometry.vessel_outline(**_WALL)  # synthetic/other device
    return {"r": rs.round(4).tolist(), "z": zs.round(4).tolist(),
            "label": "vessel outline (approx.)"}


def load_sensors() -> list[dict]:
    """All DIII-D sensors as flat records, from the bundled layout table."""
    sensors: list[dict] = []
    for line in _TABLE.read_text().splitlines():
        cols = line.split()
        if len(cols) < 7 or cols[0].lower() == "channel":
            continue
        try:
            r, z, phi, tilt, length, dphi = (float(cols[i]) for i in range(1, 7))
        except ValueError:
            continue  # header / malformed row
        sensors.append(_record(cols[0], r, z, phi, tilt, length, dphi,
                               kind=_kind(_family(cols[0]))))
    return sensors
>>>>>>> Stashed changes


def _synth_sets(sensors: list[dict]) -> list[dict]:
    """Stand-in sensor_sets for the bundled fallback (no curated sets): one
    'All <kind>' roll-up per kind, then one set per family/array."""
    by_kind: dict[str, list[str]] = {}
    by_family: dict[str, list[str]] = {}
    for s in sensors:
        by_kind.setdefault(s["kind"], []).append(s["name"])
        by_family.setdefault(s["family"], []).append(s["name"])
    out = [{"name": f"All {k}", "kind": k, "count": len(v), "sensors": v}
           for k, v in by_kind.items()]
    out += [{"name": fam, "kind": _kind(fam), "count": len(v), "sensors": v}
            for fam, v in by_family.items()]
    return out


def _from_bundled() -> dict:
    sensors = load_sensors()
    return {"device": "DIII-D", "sensors": sensors,
            "wall": _fallback_wall(), "arrays": _arrays(sensors),
            "sensor_sets": _synth_sets(sensors)}


# ── shared ───────────────────────────────────────────────────────────────────
def _arrays(sensors: list[dict]) -> list[dict]:
    """One summary row per family, in first-seen order."""
    seen: dict[str, dict] = {}
    for s in sensors:
        fam = s["family"]
        if fam not in seen:
            seen[fam] = {"family": fam, "kind": s["kind"], "shape": s["shape"], "count": 0}
        seen[fam]["count"] += 1
    return list(seen.values())


def device_geometry(name: str = "diiid") -> dict:
<<<<<<< Updated upstream
    """The full static device geometry from ``data/device/<name>.json``:
    sensors, the first-wall outline, an array summary, and the named sensor sets."""
    doc = json.loads(_device_json(name).read_text())
    sets_raw = doc.get("sensor_sets", {})
    kind_by_name = _kind_map_from_sets(sets_raw)
    sensors: list[dict] = []
    for ch, v in doc.get("sensors", {}).items():
        try:
            sensors.append(_record(
                ch, v["r"], v["z"], v["phi"], v.get("tilt", 0.0),
                v.get("length", 0.0), v.get("delta_phi", 1.0),
                kind=kind_by_name.get(ch) or _kind(_family(ch))))
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed rows
    wall = doc.get("wall") or {}
    device = doc.get("name", name)
    return {
        "device": device,
        "sensors": sensors,
        "wall": {"r": wall.get("r", []), "z": wall.get("z", []),
                 "label": f"{device} first wall"},
        "arrays": _arrays(sensors),
        "sensor_sets": _build_sets(sets_raw),
    }
=======
    """The full static device geometry: sensors, the vessel outline, array summary.

    Prefers the canonical ``data/device/<name>.json``; falls back to the bundled
    table when that file isn't present yet.
    """
    path = _device_json(name)
    if path is not None:
        try:
            return _from_json(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass  # unreadable/invalid → fall back
    return _from_bundled()
>>>>>>> Stashed changes
