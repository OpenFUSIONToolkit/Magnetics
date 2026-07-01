#!/usr/bin/env python3
"""Regenerate src/magnetics/data/device/kstar.json.

Two provenance sources:
  * MC1T toroidal Mirnov array — SHOT-AWARE, from kstar_mirnov_config.json (copied
    from nkstar /PRISM/mirnov_archive): per-channel toroidal angle + per-campaign-year
    polarity signs (1 normal / -1 reversed / 0 excluded) + the MC1T10->MC1P03 rename
    for year>=2017. Mirrors scripts/kstar/check_mirnov_size.py:get_channels().
  * Everything else (poloidal Mirnov, MP probes, SL/LM, FL/LV, RC/VCM, PCMCTL) —
    manual-derived from the KSTAR Diagnostics Data User Guide v.20241211 (pp.12-32);
    angles filled where the manual states them per array.

Run from repo root:  uv run python scripts/kstar/build_kstar_device.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEVDIR = ROOT / "src/magnetics/data/device"
CONFIG = DEVDIR / "kstar_mirnov_config.json"
OUT = DEVDIR / "kstar.json"

sensors: dict = {}
GROUPMETA: dict = {}

# ── USER-SUPPLIED GEOMETRY ────────────────────────────────────────────────────
# These are the ONLY external inputs still missing for KSTAR feature-parity with
# DIII-D. Fill them from the KSTAR Diagnostics Data User Guide / the EFIT sensor
# geometry file. Everything downstream (poloidal-m fits, the SLCONTOUR spatial
# fit, the Sensors R-Z map) is already wired to consume them — no further code
# change is needed once the numbers are entered here.
#
# SENSOR_GEOM: per-sensor-tag geometry merged into that sensor's active segment.
#   Supply theta (deg) for the poloidal Mirnov array (MC1P*/MC2P*) — OR supply
#   (r, z) [m] and let nodes._set_channels derive theta = atan2(z, r-R0). Supply
#   (r, z[, tilt, length, delta_phi]) for the QS groups (LM/SL/MP) so the
#   SLCONTOUR fit and R-Z map light up.
SENSOR_GEOM: dict[str, dict] = {
    # "MC1P01": {"theta": 10.0},                  # poloidal angle only
    # "MC1P02": {"r": 2.34, "z": 0.19},           # r/z -> theta derived downstream
    # "\\MAGNETIC::TOP.LOCKED_MODE:LM01": {"r": 2.30, "z": 0.0, "phi": 0.0},
}
# First-wall / vessel / coil contours (metres). Emitted only when non-empty, so
# regenerating today reproduces the current wall-less config with no regression.
FIRST_WALL: dict = {}  # {"r": [...], "z": [...]}
VACUUM_VESSEL: dict = {}  # {"plates": [{"r": [...], "z": [...]}, ...]}
COILS: dict = {}  # {"sets": [{"name","count","turns","rz": {"r":[...],"z":[...]}}, ...]}


def _apply_sensor_geom():
    """Merge SENSOR_GEOM into each named sensor's active (first) segment."""
    for tag, geom in SENSOR_GEOM.items():
        rec = sensors.get(node(tag))
        if rec is None:
            raise SystemExit(f"SENSOR_GEOM tag is not a known sensor: {tag}")
        seg = rec["segments"][0]
        for k in ("phi", "theta", "r", "z", "tilt", "length", "delta_phi"):
            if geom.get(k) is not None:
                seg[k] = round(float(geom[k]), 4)


def node(tag):
    return tag if tag.startswith("\\") else "\\" + tag


def add(
    tag,
    *,
    phi=None,
    theta=None,
    r=None,
    z=None,
    tilt=None,
    length=None,
    delta_phi=None,
    gain=None,
    pointname=None,
):
    seg = {"since_shot": 0}
    if phi is not None:
        seg["phi"] = round(float(phi), 3)
    if theta is not None:
        seg["theta"] = round(float(theta), 3)
    if r is not None:
        seg["r"] = round(float(r), 4)
    if z is not None:
        seg["z"] = round(float(z), 4)
    if tilt is not None:
        seg["tilt"] = round(float(tilt), 3)
    if length is not None:
        seg["length"] = round(float(length), 4)
    if delta_phi is not None:
        seg["delta_phi"] = round(float(delta_phi), 3)
    if gain is not None:
        seg["gain"] = float(gain)
    if pointname is not None:
        seg["pointname"] = node(pointname)
    sensors[node(tag)] = {"segments": [seg]}
    return node(tag)


def add_segmented(tag, segments):
    sensors[node(tag)] = {"segments": segments}
    return node(tag)


def rng(prefix, lo, hi, suffix="", width=2):
    return [f"{prefix}{i:0{width}d}{suffix}" for i in range(lo, hi + 1)]


# ── MC1T toroidal array — shot-aware, from the config ────────────────────────
cfg = json.loads(CONFIG.read_text())
names = cfg["channel_names"]  # MC1T01..MC1T20
angles = cfg["toroidal_angles"]
signs_by_year = cfg["yearly_signs"]
# year ranges sorted by start shot (skip the _comment key)
year_ranges = sorted(
    ((int(y), v[0]) for y, v in cfg["shot_year_ranges"].items() if not y.startswith("_")),
    key=lambda t: t[1],
)


def _state(ch_i, year):
    """(pointname, gain) for channel index ch_i in a campaign year, mirroring
    check_mirnov_size.get_channels(): sign 0 -> excluded; ch9->MC1P03 for year>=2017."""
    signs = signs_by_year.get(str(year), signs_by_year["default"])
    sign = signs[ch_i]
    if sign == 0:
        return ("NotAvailable", None)
    name = "MC1P03" if (ch_i == 9 and year >= 2017) else names[ch_i]
    return (node(name), sign)


mc1t_nodes = []
for i, name in enumerate(names):
    segs = []
    last = None
    for year, start in year_ranges:
        pn, gain = _state(i, year)
        state = (pn, gain)
        if state == last:
            continue  # collapse consecutive identical eras
        last = state
        if gain is None:  # excluded this era
            segs.append({"since_shot": start, "pointname": "NotAvailable"})
        else:
            seg = {"since_shot": start, "phi": round(float(angles[i]), 3), "gain": float(gain)}
            if pn != node(name):  # renamed (MC1T10 -> MC1P03)
                seg["pointname"] = pn
            segs.append(seg)
    # first segment always covers from shot 0
    if segs:
        segs[0]["since_shot"] = 0
    mc1t_nodes.append(add_segmented(node(name), segs))
GROUPMETA["mirnov_toroidal"] = {
    "unit": "T/s",
    "sampling_khz": 2000,
    "description": "MC Mirnov toroidal array (dBz/dt) for toroidal mode number n; "
    "shot-aware angles+polarity from kstar_mirnov_config.json",
}

# ── everything else — manual-derived (KSTAR Diagnostics Manual pp.12-32) ─────
sets: dict = {"mirnov_toroidal": mc1t_nodes}

# MC poloidal array (theta per-channel NOT in the manual)
mc_pol = (
    rng("MC1P", 1, 6)
    + ["MC1P08"]
    + rng("MC1P", 10, 13)
    + rng("MC1P", 15, 17)
    + rng("MC1P", 20, 22)
    + ["MC2P10", "MC2P11"]
)
pol_flip = {
    "MC1P01",
    "MC1P02",
    "MC1P03",
    "MC1P04",
    "MC1P06",
    "MC1P10",
    "MC1P11",
    "MC1P15",
    "MC1P17",
    "MC2P11",
}
sets["mirnov_poloidal"] = [add(p, gain=-1.0 if p in pol_flip else None) for p in mc_pol]
GROUPMETA["mirnov_poloidal"] = {
    "unit": "T/s",
    "sampling_khz": 2000,
    "description": "MC Mirnov poloidal array (dBz/dt) for poloidal mode number m",
}

# NTM-control coils (toroidal angles given)
ntm = {"PCMCTL01": 2.0, "PCMCTL02": 92.0, "PCMCTL05": 182.0, "PCMCTL09": 212.0}
sets["ntm_control"] = [add(t, phi=phi) for t, phi in ntm.items()]
GROUPMETA["ntm_control"] = {
    "unit": "T/s",
    "sampling_khz": 100,
    "description": "MC NTM-control coils",
}

# LM / SL (QS/SLCONTOUR)
# Locked-mode nodes are tree-qualified in the MAGNETIC tree (from KDT helpers.py).
sets["locked_mode"] = [add(f"\\MAGNETIC::TOP.LOCKED_MODE:LM{i:02d}") for i in range(1, 5)]
GROUPMETA["locked_mode"] = {
    "unit": "Wb",
    "sampling_khz": 20,
    "description": "LM locked-mode coils (radial flux, midplane); Br=Fr/0.4603",
}
sl = []
for pre, phi in {"SL1P": 67.5, "SL2P": 157.5, "SL3P": 247.5, "SL4P": 337.5}.items():
    sl += [add(t, phi=phi) for t in rng(pre, 1, 10)]
sets["saddle_loops"] = sl
GROUPMETA["saddle_loops"] = {
    "unit": "Wb",
    "sampling_khz": 20,
    "description": "SL saddle loops (vertical flux); 4 toroidal banks",
}

# FL / LV
sets["flux_loops"] = [add(t) for t in rng("FL", 1, 45)]
GROUPMETA["flux_loops"] = {
    "unit": "Wb",
    "sampling_khz": 20,
    "description": "FL poloidal flux loops",
}
sets["loop_voltage"] = [add(t) for t in ["LV01", "LV12", "LV23", "LV34", "LV45"]]
GROUPMETA["loop_voltage"] = {"unit": "V", "sampling_khz": 20, "description": "LV loop voltage"}

# MP probes (per-array toroidal angle stated; poloidal position not)
mp = []
for pre, phi in [("MP4P", 255.9), ("MP1P", 31.1)]:
    mp += [add(t, phi=phi) for t in rng(pre, 1, 42, "Z")]
    mp += [add(t, phi=phi) for t in rng(pre, 1, 42, "R")]
mp += [add(t, phi=255.9) for t in rng("MP4P", 43, 45, "Z") + rng("MP4P", 50, 52, "Z")]
mp += [add(t, phi=324.0) for t in rng("PLMP", 1, 4, "Z")]
mp += [add(t, phi=324.6) for t in rng("MP5P", 1, 42, "Z")]
mp += [add(t, phi=324.6) for t in rng("MP5P", 6, 16, "R") + rng("MP5P", 27, 37, "R")]
mpz = {
    "MPZ028": [28.0, ["U03", "U04", "L20"]],
    "MPZ049": [49.0, ["U04", "L20"]],
    "MPZ118": [118.0, ["U03", "U04", "L20"]],
    "MPZ142": [142.0, ["U04", "L20"]],
    "MPZ208": [208.0, ["U03", "U04", "L20"]],
    "MPZ229": [229.0, ["U04", "L20"]],
    "MPZ298": [298.0, ["U03", "U04", "L20"]],
    "MPZ322": [322.0, ["U04", "L20"]],
}
for base, (phi, chs) in mpz.items():
    mp += [add(base + c, phi=phi) for c in chs]
sets["poloidal_field_probes"] = mp
GROUPMETA["poloidal_field_probes"] = {
    "unit": "T",
    "sampling_khz": 20,
    "description": "MP integrated poloidal-field probes (Bz tangential, Br normal)",
}

# RC / VCM
sets["plasma_current"] = [add(t) for t in ["RC01", "RC02", "RC03"]]
sets["total_current"] = [add(t) for t in ["VCM01", "VCM02", "VCM03"]]
GROUPMETA["plasma_current"] = {
    "unit": "A",
    "sampling_khz": 20,
    "description": "RC Rogowski plasma current",
}
GROUPMETA["total_current"] = {
    "unit": "A",
    "sampling_khz": 20,
    "description": "VCM total toroidal current",
}

# composites the analyses consume
sets["rotating"] = {"type": "composite", "sets": ["mirnov_toroidal", "mirnov_poloidal"]}
sets["quasi_stationary"] = {
    "type": "composite",
    "sets": ["locked_mode", "saddle_loops", "poloidal_field_probes"],
}

sensor_sets = {
    k: (v if isinstance(v, dict) else {"type": "list", "sensors": v}) for k, v in sets.items()
}

# Per-group MDS tree (metadata the fetcher consults; see toksearch._node_tree_map).
# CONFIRMED: MC Mirnov -> 'kstar' (from /PRISM archive openTree('kstar')), locked-mode ->
# 'MAGNETIC' (KDT helpers.py). INFERRED (same magnetics family, unconfirmed): SL/FL/LV/MP.
TREES = {
    "mirnov_toroidal": "kstar",
    "mirnov_poloidal": "kstar",
    "ntm_control": "kstar",
    "locked_mode": "MAGNETIC",
    "saddle_loops": "MAGNETIC",
    "flux_loops": "MAGNETIC",
    "loop_voltage": "MAGNETIC",
    "poloidal_field_probes": "MAGNETIC",
    "plasma_current": "MAGNETIC",
    "total_current": "MAGNETIC",
}
for _g, _t in TREES.items():
    if _g in GROUPMETA:
        GROUPMETA[_g]["tree"] = _t

_apply_sensor_geom()

with_geom = sum(
    1 for s in sensors.values() if any("phi" in seg or "theta" in seg for seg in s["segments"])
)

ALERTS = [
    "MC Mirnov POLOIDAL array (MC1P/MC2P) per-channel angles (theta) are MISSING — the "
    "copied /PRISM/mirnov_archive covers only the toroidal (N-mode) system. Poloidal "
    "sensors are node-only. (The toroidal MC1T angles + polarity ARE populated, shot-aware, "
    "from kstar_mirnov_config.json.)",
    "MDS trees CONFIRMED only for MC Mirnov ('kstar', from the archive) and locked-mode "
    "('MAGNETIC', from KDT helpers.py). signal_groups[*].tree for SL/FL/LV/MP is INFERRED "
    "(MAGNETIC family) and must be confirmed before fetching those groups.",
    "MC sampling is 2 MHz — large data volume; expect to window/decimate on pull.",
    "MP array channel ranges (e.g. MP4P01-42) are expanded uniformly; some individual "
    "channels may not exist for a given shot. MP poloidal positions (theta/r/z) not provided.",
    "No wall / vacuum-vessel / coil geometry for KSTAR yet (Sensors view will lack a wall).",
    "Plasma pointnames use PCS_KSTAR (Ip, B_T) and efitrt1 (elongation/q95/betaN) per KDT; "
    "the efitrt1 elongation node itself is a best-guess ('\\kappa').",
]

doc = {
    "name": "KSTAR",
    "R0": 1.8,
    "access": "mdsplus_tree",
    "tree": "kstar",
    "server": "mdsr.kstar.kfe.re.kr:8005",
    "gateway": "",
    "note": "KSTAR magnetics config. MC1T toroidal array is shot-aware from "
    "kstar_mirnov_config.json (/PRISM/mirnov_archive); other groups are from the "
    "KSTAR Diagnostics Data User Guide v.20241211 (pp.12-32). Sensor keys are MDS+ "
    "node tags; fetch is tree-based (per-signal openTree), not PTDATA. KSTAR signals "
    "span multiple trees (see signal_groups[*].tree + plasma pointnames). Reached via "
    "the KFE VPN + nkstar tunnel (see 'connection'); device-level 'tree' is the "
    "Mirnov default 'kstar'.",
    "connection": {
        "transport": "kstar_transport",
        "vpn_url": "https://vpn.kfe.re.kr",
        "vpn_executable_candidates": [
            "/opt/cisco/secureclient/bin/vpn",
            "/opt/cisco/anyconnect/bin/vpn",
        ],
        "ssh_host": "nkstar.kstar.kfe.re.kr",
        "ssh_port": 2201,
        "mds_host": "mdsr.kstar.kfe.re.kr",
        "mds_port": 8005,
        "local_port": 8005,
        "username_scheme": "VPN username is 'k-<id>'; SSH/MDS username is '<id>' (VPN adds a "
        "'k-' prefix to the same account id).",
        "note": "Reached only via the KFE VPN + nkstar SSH tunnel; see "
        "magnetics.data.fetch.kstar_transport.session(). No credentials stored here.",
    },
    "plasma pointnames": {
        "current": {
            "name": "Ip",
            "tree": "PCS_KSTAR",
            "node": "\\PCS_KSTAR::TOP:PC:PCRC03*(-1)*(1e-6)",
        },
        "toroidal field": {
            "name": "B_T",
            "tree": "PCS_KSTAR",
            "node": "\\PCS_KSTAR::TOP:PC:PCITFMSRD",
        },
        "elongation": {"name": "kappa", "tree": "efitrt1"},
    },
    "arrays": {"toroidal": "mirnov_toroidal", "poloidal": "mirnov_poloidal"},
    # Default sensor set for the SLCONTOUR quasi-stationary fit (nodes._prep_qs_ds
    # reads this so KSTAR uses its own composite instead of DIII-D's Bp_LFS_midplane).
    "qs_default_set": "quasi_stationary",
    # Point-sensor spatial basis: KSTAR geometry is r/z/phi only (no extended-loop
    # tilt/length yet), so the fit models each sensor as a point rather than DIII-D's
    # extended-loop "sinusoidal-integral". Upgrade to integral once tilt/length land.
    "qs_fit_basis": "sinusoidal-point",
    "signal_groups": GROUPMETA,
    "alerts": ALERTS,
    "sensors": sensors,
    "sensor_sets": sensor_sets,
    "geometry_note": "MC1T toroidal: phi + polarity (gain) per shot era, from the config. "
    "MP/SL/PCMCTL/RC: per-array toroidal phi from the manual. MC1P/MC2P, "
    "FL, LM: node-only unless populated via SENSOR_GEOM in the builder "
    "(theta and/or r/z). Wall/vessel/coils emitted from FIRST_WALL / "
    "VACUUM_VESSEL / COILS when supplied.",
}

# Segmented geometry blocks (mirror diiid.json). Emitted only when supplied above,
# so an unpopulated build stays byte-for-byte wall-less (no regression).
if FIRST_WALL:
    doc["first_wall"] = {"segments": [{"since_shot": 0, **FIRST_WALL}]}
    doc["wall"] = {"r": FIRST_WALL["r"], "z": FIRST_WALL["z"]}
if VACUUM_VESSEL:
    doc["vacuum_vessel"] = {"segments": [{"since_shot": 0, **VACUUM_VESSEL}]}
if COILS:
    doc["coils"] = {"segments": [{"since_shot": 0, **COILS}]}

OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
print(f"wrote {OUT.relative_to(ROOT)}")
print(f"sensors: {len(sensors)}  (with phi/theta: {with_geom})")
print(f"MC1T shot-aware channels: {len(mc1t_nodes)}  e.g. segments for \\MC1T10:")
print(json.dumps(sensors["\\MC1T10"]["segments"], indent=1))
