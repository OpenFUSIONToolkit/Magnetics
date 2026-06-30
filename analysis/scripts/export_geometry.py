"""Regenerate the Sensors-view geometry fixtures from the real DIII-D table.

    uv run python scripts/export_geometry.py

Reads the static device geometry (data/diiid_geometry.py) and writes one
`geometry` kind-node per mock machine into gui/web/public/mock/<machine>/.

The node is a normal `scatter2d` (points = the R-Z scatter, so the generic
<NodeView> still renders a cross-section), enriched with the full per-sensor
records + the vessel outline in `meta`. The Sensors tab reads `meta` to draw the
wall, point probes, and saddle loops. `meta` is the contract's untyped extension
hatch, so this needs no change to contract.ts / contracts.py.

These are mock fixtures (dev aids): both mock machines get the same full device
layout, since the sensor geometry is static and shot-independent.
"""
from __future__ import annotations

import json
from pathlib import Path

from magnetics.core import contracts
from magnetics.data import diiid_geometry

# repo_root/analysis/scripts/export_geometry.py -> repo_root
_MOCK = Path(__file__).resolve().parents[2] / "gui" / "web" / "public" / "mock"
_MACHINES = ("MOCK-A", "MOCK-B")


def build_node() -> dict:
    geo = diiid_geometry.device_geometry()
    sensors = geo["sensors"]
    points = [{"x": s["r"], "y": s["z"], "label": s["name"], "group": s["kind"]}
              for s in sensors]
    return contracts.scatter2d(
        points, {"x": "R (m)", "y": "Z (m)"},
        meta={
            "n_sensors": len(sensors),
            "device": geo["device"],
            "sensors": sensors,
            "wall": geo["wall"],
            "arrays": geo["arrays"],
        },
    )


def main() -> None:
    node = build_node()
    for machine in _MACHINES:
        out = _MOCK / machine / "geometry.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(node))
        print(f"wrote {out}  ({node['meta']['n_sensors']} sensors)")


if __name__ == "__main__":
    main()
