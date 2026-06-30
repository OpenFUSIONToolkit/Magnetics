"""DIII-D static sensor geometry, loaded from the published layout table.

`diiid_sensors.txt` is the genuine device geometry table (one row per channel):

    channel   r   z   phi   tilt   length   delta_phi   na   pair

where (r, z) is the sensor position in the poloidal plane [m], `phi` its toroidal
angle [deg], `length` its poloidal size [m], and `delta_phi` its toroidal extent
[deg]. Point probes (Mirnov Bp) have delta_phi ~ 1 deg; saddle loops span tens of
degrees toroidally — that extent is what lets the GUI draw them as real loops
rather than dots.

Device specifics (the family -> sensor-kind mapping, the schematic wall size) live
HERE; the GUI only ever sees generic (r, z, phi, length, delta_phi) numbers, so the
Sensors view stays device-agnostic. A different machine ships its own loader with
the same output shape.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core import geometry

_TABLE = Path(__file__).with_name("diiid_sensors.txt")
_WALL_FILE = Path(__file__).with_name("diiid_wall.txt")

# Fallback vessel cross-section (Miller D-shape) for devices with no wall file.
_WALL = dict(r0=1.70, a=0.75, kappa=1.85, delta=0.45)

# A loop is anything with real toroidal extent; everything else is a point probe.
_LOOP_MIN_DPHI = 5.0


def _kind(family: str) -> str:
    """Map a DIII-D family prefix to the contract's Bp | Br | coil vocabulary."""
    if family.startswith("MPI"):
        return "Bp"          # Mirnov poloidal-field probes (point)
    if family.startswith(("ISL", "ESL")):
        return "Br"          # internal/external saddle loops
    return "coil"            # I-coils, C-coils, control/error-field coils


def _family(channel: str) -> str:
    m = re.match(r"^[A-Za-z]+", channel)
    return m.group(0) if m else channel


def _parse_namelist_array(text: str) -> list[float]:
    """Parse a Fortran-namelist numeric array, honouring ``N*value`` repeats."""
    vals: list[float] = []
    for tok in text.replace(",", " ").split():
        if tok in ("/", "&end", "&END"):
            break
        try:
            if "*" in tok:
                n, v = tok.split("*")
                vals += [float(v)] * int(n)
            else:
                vals.append(float(tok))
        except ValueError:
            break
    return vals


def _real_wall() -> tuple[list[float], list[float]] | None:
    """The measured DIII-D first-wall (r, z) outline from the ``&wall`` namelist,
    or None if the file isn't present."""
    if not _WALL_FILE.exists():
        return None
    raw = _WALL_FILE.read_text()
    if "&wall" not in raw:
        return None
    body = raw.split("&wall", 1)[1]
    try:
        rpart = body.split("r =", 1)[1].split("z =", 1)[0]
        zpart = body.split("z =", 1)[1]
    except IndexError:
        return None
    r, z = _parse_namelist_array(rpart), _parse_namelist_array(zpart)
    n = min(len(r), len(z))
    return (r[:n], z[:n]) if n else None


def load_sensors() -> list[dict]:
    """All DIII-D sensors as flat records: name, family, kind, shape, and the
    raw geometry (phi, r, z, length, delta_phi, tilt)."""
    sensors: list[dict] = []
    for line in _TABLE.read_text().splitlines():
        cols = line.split()
        if len(cols) < 7 or cols[0].lower() == "channel":
            continue
        name = cols[0]
        try:
            r, z, phi, tilt, length, dphi = (float(cols[i]) for i in range(1, 7))
        except ValueError:
            continue  # header / malformed row
        family = _family(name)
        sensors.append({
            "name": name,
            "family": family,
            "kind": _kind(family),
            "shape": "loop" if dphi > _LOOP_MIN_DPHI else "point",
            "phi": phi,
            "r": r,
            "z": z,
            "length": length,
            "delta_phi": dphi,
            "tilt": tilt,
        })
    return sensors


def _arrays(sensors: list[dict]) -> list[dict]:
    """One summary row per family, in first-seen order."""
    seen: dict[str, dict] = {}
    for s in sensors:
        fam = s["family"]
        if fam not in seen:
            seen[fam] = {"family": fam, "kind": s["kind"], "shape": s["shape"], "count": 0}
        seen[fam]["count"] += 1
    return list(seen.values())


def device_geometry() -> dict:
    """The full static device geometry: sensors, the vessel outline, array summary."""
    sensors = load_sensors()
    wall = _real_wall()
    if wall is not None:
        rw, zw = wall
        wall_node = {"r": rw, "z": zw, "label": "DIII-D first wall"}
    else:  # synthetic / other device: fall back to the schematic D-shape
        rs, zs = geometry.vessel_outline(**_WALL)
        wall_node = {"r": rs.round(4).tolist(), "z": zs.round(4).tolist(),
                     "label": "vessel outline (approx.)"}
    return {
        "device": "DIII-D",
        "sensors": sensors,
        "wall": wall_node,
        "arrays": _arrays(sensors),
    }
