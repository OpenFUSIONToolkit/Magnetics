#!/usr/bin/env python3
"""Import machine structure into the committed device tables.

Adds first wall + vacuum vessel (from TokaMaker Grad-Shafranov geometry, an OFT
solver) and perturbation coils (from GPEC Fortran coil files) into
``src/magnetics/data/device/<device>.json``, as **shot-segmented** geometry
matching the existing ``wall``/``sensors`` mechanism (a ``segments`` list keyed by
``since_shot``).

Sources are vendored under ``scripts/geometry_sources/`` for reproducibility:
  - ``<machine>_tokamaker.json`` — ``{limiter: [[R,Z]...], vv: ..., coils: ...}``
  - ``coils/<set>.dat``          — GPEC coil files: header ``ncoil s nsec nw``
    then ``ncoil*s*nsec`` ``x y z`` lines (meters); each coil is one 3D loop.

Fields added to each device JSON:
  - ``first_wall``    : ``{segments: [{since_shot, r[], z[]}]}``
  - ``vacuum_vessel`` : ``{segments: [{since_shot, plates: [{r[], z[]}]}]}``
  - ``coils``         : ``{segments: [{since_shot, sets: [
        {name, count, turns, rz: {r[], z[]}, loops: [[[x,y,z]...]]}]}]}``
    (``turns`` is the signed winding count nw; sign = winding direction)
    where ``rz`` is ONE representative coil's R-Z footprint (the GUI draws a single
    coil per set, not all of them) and ``loops`` keeps every coil's 3D path.

NSTX and NSTX-U share ``nstx.json``, split at ``since_shot`` NSTXU_SINCE_SHOT.
This boundary is a PLACEHOLDER — see issue #42.

Run:  uv run python scripts/import_device_geometry.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "geometry_sources"
_DEVICE_DIR = _HERE.parent / "src" / "magnetics" / "data" / "device"

#: NSTX -> NSTX-U geometry boundary. PLACEHOLDER — confirm (issue #42).
NSTXU_SINCE_SHOT = 200000

#: Keep 3D coil loops light (they render smoothly well below full resolution).
_LOOP_MAX_PTS = 64


# ── GPEC coil files ──────────────────────────────────────────────────────────
def parse_coils(path: Path) -> tuple[list[list[list[float]]], float]:
    """A GPEC coil file -> ``(coils, turns)``: a list of coils (each a list of
    ``[x, y, z]`` points) and the signed winding count ``nw`` (turns per coil;
    the sign encodes winding direction)."""
    lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
    ncoil, s, nsec, nw = (
        int(lines[0].split()[0]),
        int(lines[0].split()[1]),
        int(lines[0].split()[2]),
        float(lines[0].split()[3]),
    )
    pts = [[float(v) for v in ln.split()] for ln in lines[1:]]
    per = s * nsec
    if len(pts) != ncoil * per:
        raise ValueError(f"{path.name}: expected {ncoil * per} points, got {len(pts)}")
    return [pts[i * per : (i + 1) * per] for i in range(ncoil)], nw


def _downsample(seq: list, n: int) -> list:
    if len(seq) <= n:
        return seq
    step = len(seq) / n
    return [seq[int(i * step)] for i in range(n)] + [seq[-1]]


def coilset(name: str, path: Path) -> dict:
    """A coil file -> a set record: one representative coil's R-Z footprint plus
    every coil's (downsampled) 3D loop."""
    coils, turns = parse_coils(path)
    rep = coils[0]  # the GUI draws a single coil per set as an R-Z footprint
    rz = {
        "r": [round(math.hypot(x, y), 4) for x, y, _ in rep],
        "z": [round(z, 4) for _, _, z in rep],
    }
    loops = [
        [[round(x, 4), round(y, 4), round(z, 4)] for x, y, z in _downsample(c, _LOOP_MAX_PTS)]
        for c in coils
    ]
    return {"name": name, "count": len(coils), "turns": turns, "rz": rz, "loops": loops}


# ── TokaMaker first wall + vacuum vessel ─────────────────────────────────────
def first_wall(tok: dict) -> dict:
    """The limiter polyline -> ``{r[], z[]}`` (closed)."""
    rz = tok["limiter"]
    r = [round(p[0], 4) for p in rz]
    z = [round(p[1], 4) for p in rz]
    if (r[0], z[0]) != (r[-1], z[-1]):
        r.append(r[0])
        z.append(z[0])
    return {"r": r, "z": z}


def vacuum_vessel(tok: dict) -> list[dict]:
    """Normalize the (per-machine) ``vv`` into a list of closed ``{r[], z[]}``
    plate polygons. DIII-D: ``[[quad(4 [R,Z]), thickness], ...]``; NSTX-U:
    ``{name: {contour: [[R,Z]...]}}``; NSTX: absent."""
    vv = tok.get("vv")
    plates: list[dict] = []
    if not vv:
        return plates
    contours: list[list] = []
    if isinstance(vv, dict):  # NSTX-U: named plates
        contours = [p["contour"] for p in vv.values() if isinstance(p, dict) and "contour" in p]
    else:  # DIII-D: [quad, thickness] pairs
        contours = [item[0] for item in vv if item and isinstance(item[0], list)]
    for c in contours:
        r = [round(p[0], 4) for p in c]
        z = [round(p[1], 4) for p in c]
        if (r[0], z[0]) != (r[-1], z[-1]):
            r.append(r[0])
            z.append(z[0])
        plates.append({"r": r, "z": z})
    return plates


# ── merge into a device JSON ─────────────────────────────────────────────────
def _load(name: str) -> dict:
    return json.loads((_SRC / name).read_text())


def write_device(device: str, segments: list[dict]) -> None:
    """Merge first_wall/vacuum_vessel/coils segment lists into <device>.json."""
    path = _DEVICE_DIR / f"{device}.json"
    dev = json.loads(path.read_text())
    dev["first_wall"] = {
        "segments": [{"since_shot": s["since_shot"], **s["first_wall"]} for s in segments]
    }
    dev["vacuum_vessel"] = {
        "segments": [
            {"since_shot": s["since_shot"], "plates": s["vacuum_vessel"]} for s in segments
        ]
    }
    dev["coils"] = {
        "segments": [{"since_shot": s["since_shot"], "sets": s["coils"]} for s in segments]
    }
    path.write_text(json.dumps(dev, indent=2) + "\n")
    fw = segments[0]["first_wall"]
    print(
        f"{device}.json: {len(segments)} segment(s); "
        f"first_wall {len(fw['r'])} pts, "
        f"vv {sum(len(s['vacuum_vessel']) for s in segments)} plates, "
        f"coils {sum(len(s['coils']) for s in segments)} sets"
    )


def main() -> None:
    coil_dir = _SRC / "coils"

    # DIII-D: single geometry era.
    diiid_tok = _load("diiid_tokamaker.json")
    write_device(
        "diiid",
        [
            {
                "since_shot": 0,
                "first_wall": first_wall(diiid_tok),
                "vacuum_vessel": vacuum_vessel(diiid_tok),
                "coils": [
                    coilset("C", coil_dir / "d3d_c.dat"),
                    coilset("IU", coil_dir / "d3d_iu.dat"),
                    coilset("IL", coil_dir / "d3d_il.dat"),
                ],
            }
        ],
    )

    # NSTX + NSTX-U: one file, split by shot. RWM-EF coils apply to both eras.
    rwmef = coilset("RWMEF", coil_dir / "nstx_rwmef.dat")
    write_device(
        "nstx",
        [
            {
                "since_shot": 0,
                "first_wall": first_wall(_load("nstx_tokamaker.json")),
                "vacuum_vessel": vacuum_vessel(_load("nstx_tokamaker.json")),
                "coils": [rwmef],
            },
            {
                "since_shot": NSTXU_SINCE_SHOT,  # PLACEHOLDER — issue #42
                "first_wall": first_wall(_load("nstxu_tokamaker.json")),
                "vacuum_vessel": vacuum_vessel(_load("nstxu_tokamaker.json")),
                "coils": [rwmef],
            },
        ],
    )


if __name__ == "__main__":
    main()
