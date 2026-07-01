"""Shot-aware device geometry: the time-segment resolver (``devices``), the
fetcher's pointname assembly, and ``diiid``'s shot-dependent positions.

Driven by the committed device table (``magnetics.data.devices``) — no network or
fetched data.
"""

from __future__ import annotations

from magnetics.data import devices, diiid


# A synthetic device: a stable sensor, a renamed-then-moved sensor, and a
# decommissioned sensor — exercises every branch the seeded real file can't yet.
DEV = {
    "R0": 1.69,
    "sensors": {
        "S_OK": {"segments": [{"since_shot": 152472, "r": 2.0, "z": 0.0, "phi": 10.0}]},
        "S_RENAMED": {
            "segments": [
                {"since_shot": 100000, "pointname": "OLD_S", "r": 1.0, "z": 0.1, "phi": 5.0},
                {"since_shot": 180000, "r": 2.5, "z": -0.2, "phi": 7.0},
            ]
        },  # moved; pt defaults to id
        "S_GONE": {
            "segments": [
                {"since_shot": 152472, "r": 2.0, "z": 0.0, "phi": 12.0},
                {"since_shot": 190000, "pointname": "NotAvailable"},
            ]
        },
    },
}


# ── resolver: pointname_at ────────────────────────────────────────────────────
def test_pointname_in_range_is_canonical():
    assert devices.pointname_at(DEV, "S_OK", 184927) == "S_OK"


def test_pointname_below_floor_is_none():
    assert devices.pointname_at(DEV, "S_OK", 150000) is None


def test_pointname_uses_legacy_name_for_old_shot():
    assert devices.pointname_at(DEV, "S_RENAMED", 150000) == "OLD_S"
    assert devices.pointname_at(DEV, "S_RENAMED", 185000) == "S_RENAMED"


def test_since_shot_boundary_is_inclusive():
    # exactly at the new segment's since_shot, the new segment is active
    assert devices.pointname_at(DEV, "S_RENAMED", 180000) == "S_RENAMED"
    assert devices.pointname_at(DEV, "S_RENAMED", 179999) == "OLD_S"


def test_not_available_segment_is_skipped():
    assert devices.pointname_at(DEV, "S_GONE", 185000) == "S_GONE"
    assert devices.pointname_at(DEV, "S_GONE", 195000) is None
    assert devices.valid_at(DEV, "S_GONE", 195000) is False


# ── resolver: geometry_at (the actual "sensor moved" case) ────────────────────
def test_geometry_tracks_the_moved_segment():
    g_old = devices.geometry_at(DEV, "S_RENAMED", 150000)
    g_new = devices.geometry_at(DEV, "S_RENAMED", 185000)
    assert g_old["r"] == 1.0 and g_new["r"] == 2.5  # different position per era
    assert "since_shot" not in g_old and "pointname" not in g_old


def test_geometry_none_when_decommissioned_or_out_of_range():
    assert devices.geometry_at(DEV, "S_GONE", 195000) is None
    assert devices.geometry_at(DEV, "S_OK", 100000) is None


# ── fetch assembly: _resolve_pointnames (no network) ──────────────────────────
def test_fetch_resolution_recent_shot_keeps_all():
    from magnetics.data.fetch import toksearch as tf

    query, canon, skipped = tf._resolve_pointnames(
        DEV, ["S_OK", "S_RENAMED", "S_GONE", "ip"], 185000
    )
    assert query == ["S_OK", "S_RENAMED", "S_GONE", "ip"]
    assert canon["ip"] == "ip"  # unmodeled passes through
    assert skipped == []


def test_fetch_resolution_old_shot_uses_alt_and_skips():
    from magnetics.data.fetch import toksearch as tf

    query, canon, skipped = tf._resolve_pointnames(
        DEV, ["S_OK", "S_RENAMED", "S_GONE", "ip"], 150000
    )
    assert "OLD_S" in query and canon["OLD_S"] == "S_RENAMED"  # legacy name queried
    assert "ip" in query  # unmodeled still passes
    assert set(skipped) == {"S_OK", "S_GONE"}  # pre-floor sensors dropped


def test_fetch_resolution_skips_decommissioned():
    from magnetics.data.fetch import toksearch as tf

    query, _canon, skipped = tf._resolve_pointnames(DEV, ["S_GONE"], 195000)
    assert query == [] and skipped == ["S_GONE"]


# ── real device file: the three availability eras (124400 / 151593) ───────────
def test_real_file_resolves_sensors_by_era():
    from magnetics.data.fetch import toksearch as tf

    dev = devices.load_device("diiid")
    survivor = "MPID66M067"  # legacy survivor: present from 124400
    upgrade = "MPID66M020"  # upgrade-only: present from 151593
    ids = [survivor, upgrade]
    assert all(i in dev["sensors"] for i in ids), "expected known sensors in the device file"

    # Modern shot: both resolve.
    q, _c, skip = tf._resolve_pointnames(dev, ids, 184927)
    assert set(q) == set(ids) and skip == []
    # Legacy era (124400 ≤ shot < 151593): survivor resolves, upgrade-only is skipped.
    q, _c, skip = tf._resolve_pointnames(dev, ids, 147131)
    assert q == [survivor] and skip == [upgrade]
    # Pre-legacy (shot < 124400): neither is modeled.
    q, _c, skip = tf._resolve_pointnames(dev, ids, 120000)
    assert q == [] and set(skip) == set(ids)


def test_diiid_geometry_is_shot_dependent():
    # table (modern shot) vs name-parse/cosmetic fallback (pre-floor) differ
    modern = diiid.sensor("MPID79A272", 184927)
    legacy = diiid.sensor("MPID79A272", 150000)
    assert modern["theta"] != legacy["theta"]
    assert abs(modern["theta"] - 86.83) < 0.1  # real θ from (r, z)
