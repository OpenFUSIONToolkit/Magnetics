"""HBT-EP device config (``data/device/hbtep.json``).

HBT-EP is a tree-based (``mdsplus_tree``) device like NSTX: the sensor key is the
tree node path, and Bp/Br classification comes from the ``sensor_sets`` name. These
checks are config-only (no network, no fetched shot) — they guard the committed
JSON and its consumption through the device-generic geometry path.
"""

from __future__ import annotations

from magnetics.data import device_geom, devices, diiid_geometry

_SHOT = 120515  # any shot: HBT-EP geometry is a single open-ended segment
_PA1_S01P = r"\TOP.SENSORS.MAGNETIC:PA1_S01P"
_PA1_S01R = r"\TOP.SENSORS.MAGNETIC:PA1_S01R"


def test_loads_as_tree_device():
    dev = devices.load_device("hbtep")
    assert dev["name"] == "HBT-EP"
    assert dev["access"] == "mdsplus_tree"
    assert dev["tree"] == "hbtep2"
    assert len(dev["sensors"]) == 96  # PA1/PA2 × (32 poloidal + 16 radial)


def test_sensor_keys_are_tree_node_paths():
    dev = devices.load_device("hbtep")
    assert all(k.startswith(r"\TOP.SENSORS.MAGNETIC:") for k in dev["sensors"])


def test_poloidal_is_bp_radial_is_br():
    """The Sensors/analysis kind is inferred from the sensor-set name: the P array
    sets say 'Bp', the R array sets say 'Br'."""
    dg = device_geom.get("hbtep")
    assert dg.kind_of(_PA1_S01P) == "Bp"
    assert dg.kind_of(_PA1_S01R) == "Br"


def test_two_toroidal_locations():
    """PA1 and PA2 sit at two distinct toroidal angles (≈180° apart)."""
    dg = device_geom.get("hbtep")
    phi1 = dg.phi_of(_PA1_S01P, _SHOT)
    phi2 = dg.phi_of(r"\TOP.SENSORS.MAGNETIC:PA2_S01P", _SHOT)
    assert phi1 is not None and phi2 is not None
    assert round(abs(phi1 - phi2)) == 180


def test_geometry_renders_bp_and_br_with_wall():
    """The device-generic Sensors view resolves all 96 sensors (both kinds) plus a
    non-empty first-wall outline — no DIII-D-specific data needed."""
    geo = diiid_geometry.device_geometry(_SHOT, "hbtep")
    assert geo["device"] == "HBT-EP"
    assert len(geo["sensors"]) == 96
    assert {s["kind"] for s in geo["sensors"]} == {"Bp", "Br"}
    assert len(geo["wall"]["r"]) > 0
    # sensors sit on a poloidal ring about R0 ≈ 0.92 m (outboard/inboard midplane).
    rs = [s["r"] for s in geo["sensors"]]
    assert min(rs) < 0.8 < 1.05 < max(rs)


def test_bp_sensor_sets_are_full_poloidal_contours():
    """Each PA Bp set is a 32-probe poloidal contour (the SLCONTOUR/MODESPEC shape)."""
    dg = device_geom.get("hbtep")
    assert len(dg.sensor_set_members("PA1 Bp poloidal")) == 32
    assert len(dg.sensor_set_members("PA2 Bp poloidal")) == 32
