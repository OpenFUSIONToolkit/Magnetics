#!/usr/bin/env python3
"""Extend ``diiid.json`` backward through the DIII-D sensor eras (to shot 124400).

The committed ``diiid.json`` sensor table only covered the post-upgrade era (every
channel keyed ``since_shot: 152472``), so legacy shots resolved *no* geometry
(``devices.geometry_at`` → None for shot < 152472). This script re-keys each
channel's earliest segment to its true availability era, so pre-upgrade shots
fetch and plot the right sensor set at the right positions.

Two era floors (see ``scripts/geometry_sources/efit/`` and the investigation notes):
  - **124400** — the stable dense legacy set. The 33 magnetic channels that survive
    the 2014 3D upgrade, plus the perturbation/control coils (C, I-coils, and their
    control-current channels), are present from here on.
  - **151593** — the 3D-magnetics upgrade raw-signal boundary (verified exact:
    151592 last legacy, 151593 first upgraded; 101 channels appear). Every
    upgrade-only channel (the added 139/157/247-plane Bp/Br arrays, the fast
    ``MPIF``/``ISLF`` loops, the extra midplane bdots 020/132/200) starts here.

Positions: the surviving channels are **geometrically stable** across 124400→now —
EFIT's per-era ``mhdin.dat`` green tables show the midplane probes unmoved (e.g.
``MPI66M067`` = (2.413, 0.003, −89.9°) in the 124400 table and today), and the
flux loops are stable across every era. So the legacy segment carries the *current*
geometry (from ``diiid_sensors.txt``, already in the file) rather than a
fabricated per-era position. The pre-124400 eras (91000/112000, where 13 probes
were repositioned) are intentionally out of scope — that data is sparse/intermittent.

Br saddle loops (ISLD/ESLD): mhdin covers Bp probes + flux loops only, so there is
no independent shot-indexed source for the saddle loops. They did not physically
move (only the *set* grew at the upgrade), so current positions apply back to 124400.

Run:  uv run python scripts/import_diiid_eras.py
"""

from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEVICE = _HERE.parent / "src" / "magnetics" / "data" / "device" / "diiid.json"

#: Dense-legacy-set floor (I-coils online, stable geometry) and the exact 3D-upgrade
#: raw-signal boundary (151592 last legacy / 151593 first upgraded).
LEGACY_SINCE = 124400
UPGRADE_SINCE = 151593

#: The 33 magnetic-sensor channels present in the legacy era (verified at shot
#: 147131), in ``diiid.json``'s key convention: bdot as the PTDATA name (…D),
#: integrated Bp and saddle loops as the OMFIT convention name.
LEGACY_SURVIVORS = {
    # 11 midplane bdot (the upgrade added 020D / 132D / 200D)
    "MPI66M067D",
    "MPI66M097D",
    "MPI66M127D",
    "MPI66M137D",
    "MPI66M157D",
    "MPI66M247D",
    "MPI66M277D",
    "MPI66M307D",
    "MPI66M312D",
    "MPI66M322D",
    "MPI66M340D",
    # 4 integrated midplane Bp
    "MPID66M067",
    "MPID66M097",
    "MPID66M127",
    "MPID66M157",
    # 4 + 2 off-midplane integrated Bp (67A / 67B)
    "MPID67A022",
    "MPID67A037",
    "MPID67A097",
    "MPID67A157",
    "MPID67B097",
    "MPID67B157",
    # 3 + 3 + 3 internal saddle loops (Br)
    "ISLD66M072",
    "ISLD66M132",
    "ISLD66M197",
    "ISLD67A072",
    "ISLD67A132",
    "ISLD67A197",
    "ISLD67B072",
    "ISLD67B132",
    "ISLD67B197",
    # 3 external saddle loops (Br)
    "ESLD66M079",
    "ESLD66M139",
    "ESLD66M199",
}

#: Perturbation/control coils are legacy hardware (C-coils old; I-coils online by
#: 124400), so they resolve for legacy shots too. Keyed by name prefix.
COIL_PREFIXES = ("C", "IU", "IL", "PCC", "PCIU", "PCIL", "RLC")


def _is_coil(name: str) -> bool:
    return name.startswith(COIL_PREFIXES) and any(c.isdigit() for c in name)


def _since_for(name: str) -> int:
    """The availability floor for a channel: legacy (124400) for a surviving
    magnetic sensor or a coil, else the 3D-upgrade boundary (151593)."""
    if name in LEGACY_SURVIVORS or _is_coil(name):
        return LEGACY_SINCE
    return UPGRADE_SINCE


def main() -> None:
    dev = json.loads(_DEVICE.read_text())
    sensors = dev["sensors"]

    missing = [n for n in LEGACY_SURVIVORS if n not in sensors]
    if missing:
        raise SystemExit(f"survivor channels absent from diiid.json: {missing}")

    counts = {LEGACY_SINCE: 0, UPGRADE_SINCE: 0}
    for name, rec in sensors.items():
        segs = rec.get("segments")
        if not segs:  # tolerate a legacy flat record
            segs = [{k: v for k, v in rec.items()}]
            rec.clear()
            rec["segments"] = segs
        segs.sort(key=lambda s: s.get("since_shot", 0))
        since = _since_for(name)
        segs[0]["since_shot"] = since  # re-key the earliest segment to its true era
        counts[since] += 1

    dev["geometry_note"] = (
        "Sensor availability is shot-segmented: magnetic channels surviving the 2014 "
        "3D-magnetics upgrade (and the perturbation/control coils) resolve from shot "
        f"{LEGACY_SINCE} (dense legacy set); upgrade-only channels from {UPGRADE_SINCE} "
        "(exact raw-signal boundary, verified 151592/151593). Positions are the current "
        "diiid_sensors.txt geometry, which EFIT per-era mhdin.dat green tables confirm is "
        f"stable across {LEGACY_SINCE}->now for surviving probes and all flux loops. "
        "Br saddle loops (ISLD/ESLD) have no independent per-era source and are assumed "
        "static (they did not move; only the set grew). Pre-124400 eras are out of scope."
    )

    _DEVICE.write_text(json.dumps(dev, indent=2) + "\n")
    print(
        f"diiid.json: {counts[LEGACY_SINCE]} channels @ since_shot {LEGACY_SINCE} "
        f"(legacy survivors + coils), {counts[UPGRADE_SINCE]} @ {UPGRADE_SINCE} (upgrade-only)"
    )


if __name__ == "__main__":
    main()
