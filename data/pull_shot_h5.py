#!/usr/bin/env python3
"""
Simple test fetcher: pull all DIII-D magnetics pointnames for a shot and save to HDF5.

Mirrors what the OMFIT `magnetics` module does in fetch_magnetics.py, but standalone:
each pointname is read from DIII-D PTDATA via the server-side `ptdata2(...)` TDI call,
and saved into one .h5 file (one group per channel, with `data` + `time` datasets).

Default shot is 184927.

Pointname list is the full DIII-D sensor + 3D-coil set taken from the OMFIT magnetics
module (modules/magnetics/DATA/DIII-D/diiid_sensors.txt), plus `ip`/`bt` for helicity.

Requirements (not in the project deps; install into a throwaway venv):
    uv venv && uv pip install mdsthin h5py numpy

By default it SSHes into the DIII-D gateway (cybele.gat.com) first, then reaches the
mdsip server (atlas.gat.com:8000) from there via netcat -- mdsthin's `sshp://` transport.
It prompts for your GA username; the system `ssh` then prompts for your password and
2FA/Duo passcode interactively (nothing hardcoded). Use --tcp for a direct mdsip login.

Usage:
    uv run python data/pull_shot_h5.py                 # ssh cybele -> atlas, shot 184927
    uv run python data/pull_shot_h5.py --shot 184927 --gateway cybele.gat.com
    uv run python data/pull_shot_h5.py --tcp           # direct TCP mdsip (no gateway)
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import h5py

try:
    from mdsthin import Connection
except ImportError:
    sys.exit("Missing dependency: pip/uv install mdsthin  (pure-python MDSplus thin client)")

# --- All DIII-D magnetics pointnames (from diiid_sensors.txt) -----------------
# Integrated poloidal-field probes (Bp)
MPID = [
    "MPID66M020", "MPID66M067", "MPID66M097", "MPID66M127", "MPID66M157",
    "MPID66M200", "MPID66M247", "MPID66M277", "MPID66M307", "MPID66M340",
    "MPID67A022", "MPID67A037", "MPID67A052", "MPID67A097", "MPID67A157",
    "MPID67A217", "MPID67A277", "MPID67A337",
    "MPID67B022", "MPID67B037", "MPID67B052", "MPID67B097", "MPID67B157",
    "MPID67B217", "MPID67B277", "MPID67B337",
    "MPID79A072", "MPID79A147", "MPID79A222", "MPID79A272",
    "MPID79B067", "MPID79B142", "MPID79B217", "MPID79B277",
    "MPID1A011", "MPID1A049", "MPID1A109", "MPID1A139", "MPID1A199",
    "MPID1A244", "MPID1A274", "MPID1A341",
    "MPID1B011", "MPID1B049", "MPID1B109", "MPID1B139", "MPID1B199",
    "MPID1B244", "MPID1B274", "MPID1B341",
    "MPID2A199", "MPID2B199", "MPID3A199", "MPID3B199",
    "MPID4A199", "MPID4B199", "MPID5A199", "MPID5B199",
]
# Raw bdot probes (un-integrated)
MPI_BDOT = [
    "MPI66M020D", "MPI66M067D", "MPI66M097D", "MPI66M127D", "MPI66M132D",
    "MPI66M137D", "MPI66M157D", "MPI66M200D", "MPI66M247D", "MPI66M277D",
    "MPI66M307D", "MPI66M312D", "MPI66M322D", "MPI66M340D",
]
# Floor/fast Bp probes
MPIF = [
    "MPIF2A139", "MPIF2B139", "MPIF3A139", "MPIF3B139",
    "MPIF4A139", "MPIF4B139", "MPIF5A139", "MPIF5B139",
]
# Saddle loops measuring radial field (Br) -- ISLD / ISLF / ESLD
ISLD = [
    "ISLD66M017", "ISLD66M042", "ISLD66M072", "ISLD66M102", "ISLD66M132",
    "ISLD66M197", "ISLD66M252", "ISLD66M312",
    "ISLD67A017", "ISLD67A052", "ISLD67A072", "ISLD67A112", "ISLD67A132",
    "ISLD67A197", "ISLD67A252", "ISLD67A312",
    "ISLD67B017", "ISLD67B052", "ISLD67B072", "ISLD67B112", "ISLD67B132",
    "ISLD67B197", "ISLD67B252", "ISLD67B312",
    "ISLD79A072", "ISLD79A147", "ISLD79A222", "ISLD79A272",
    "ISLD79B067", "ISLD79B142", "ISLD79B217", "ISLD79B277",
    "ISLD1A011", "ISLD1A049", "ISLD1A109", "ISLD1A139", "ISLD1A199",
    "ISLD1A244", "ISLD1A274", "ISLD1A341",
    "ISLD1B011", "ISLD1B049", "ISLD1B109", "ISLD1B139", "ISLD1B199",
    "ISLD1B244", "ISLD1B274", "ISLD1B341",
    "ISLD2A199", "ISLD2B199", "ISLD3A199", "ISLD3B199",
    "ISLD4A199", "ISLD4B199", "ISLD5A199", "ISLD5B199",
]
ISLF = [
    "ISLF2A139", "ISLF2B139", "ISLF3A139", "ISLF3B139",
    "ISLF4A139", "ISLF4B139", "ISLF5A139", "ISLF5B139",
]
ESLD = [
    "ESLD66M019", "ESLD66M079", "ESLD66M139",
    "ESLD66M199", "ESLD66M259", "ESLD66M319",
]
# 3D coils: C-coil, internal I-coils (upper/lower), and their PCS/RLC currents
COILS = [
    "C19", "C79", "C139", "C199", "C259", "C319",
    "IU30", "IU90", "IU150", "IU210", "IU270", "IU330",
    "IL30", "IL90", "IL150", "IL210", "IL270", "IL330",
    "PCC19", "PCC79", "PCC139", "PCC199", "PCC259", "PCC319",
    "PCIU30", "PCIU90", "PCIU150", "PCIU210", "PCIU270", "PCIU330",
    "PCIL30", "PCIL90", "PCIL150", "PCIL210", "PCIL270", "PCIL330",
    "RLC19", "RLC79", "RLC139", "RLC199", "RLC259", "RLC319",
]
# Plasma params for helicity / context
AUX = ["ip", "bt"]

POINTNAMES = MPID + MPI_BDOT + MPIF + ISLD + ISLF + ESLD + COILS + AUX


def fetch_ptdata(conn: Connection, pointname: str, shot: int):
    """Return (time, data, ok) for a PTDATA pointname via server-side ptdata2()."""
    try:
        conn.get(f'_s = ptdata2("{pointname}", {shot})')
        data = np.atleast_1d(conn.get("_s").data())
        # ptdata2 returns [0] (length-1) when the pointname has no data
        if data.size <= 1 and (data.size == 0 or data[0] == 0):
            return None, None, False
        t = np.atleast_1d(conn.get("dim_of(_s)").data())
        return t, data, True
    except Exception as exc:  # broad: we just want to know if the pull worked
        print(f"   ! {pointname}: {exc}")
        return None, None, False


def main() -> int:
    ap = argparse.ArgumentParser(description="Pull DIII-D magnetics pointnames to HDF5")
    ap.add_argument("--shot", type=int, default=184927)
    ap.add_argument("--server", default="atlas.gat.com:8000",
                    help="MDSplus (mdsip) host:port reached FROM the gateway")
    ap.add_argument("--gateway", default="cybele.gat.com",
                    help="SSH gateway host to log into first (DIII-D: cybele.gat.com)")
    ap.add_argument("--tcp", action="store_true",
                    help="connect directly over TCP mdsip instead of SSH-through-gateway")
    ap.add_argument("--out", default=None, help="output .h5 path (default shot_<shot>.h5)")
    args = ap.parse_args()

    # Prompt for the username at the command line -- nothing hardcoded.
    username = input("GA username: ").strip()
    if not username:
        sys.exit("A username is required.")

    # mdsip target (host:port), stripped of any protocol/user prefix.
    mds = args.server.split("://", 1)[-1].split("@", 1)[-1]
    mds_host, _, mds_port = mds.partition(":")
    mds_port = int(mds_port or 8000)

    out = args.out or f"shot_{args.shot}.h5"
    if args.tcp:
        # Direct mdsip: login is just the username handshake (no password server-side).
        server = f"{username}@{mds_host}:{mds_port}"
        print(f"Connecting directly to {server} (tcp mdsip) ...")
        conn = Connection(server)
    else:
        # SSH into the gateway (cybele) first, then `nc` to the mdsip server (atlas).
        # The system ssh subprocess prompts for your password + 2FA/Duo in this terminal.
        server = f"sshp://{username}@{args.gateway}:{mds_port}"
        print(f"SSH into {args.gateway} as {username}, then mdsip -> {mds_host}:{mds_port} ...")
        print("(your terminal will prompt for password and 2FA passcode)")
        conn = Connection(server, sshp_host=mds_host)
    print(f"Fetching {len(POINTNAMES)} pointnames for shot {args.shot}")

    got, missing = [], []
    with h5py.File(out, "w") as h5:
        h5.attrs["shot"] = args.shot
        h5.attrs["server"] = server
        h5.attrs["device"] = "DIII-D"
        h5.attrs["source"] = "PTDATA via ptdata2()"
        for i, pt in enumerate(POINTNAMES, 1):
            t, y, ok = fetch_ptdata(conn, pt, args.shot)
            if not ok:
                missing.append(pt)
                continue
            g = h5.create_group(pt)
            g.create_dataset("time", data=t, compression="gzip")
            g.create_dataset("data", data=y, compression="gzip")
            g.attrs["time_units"] = "ms"  # PTDATA time is in ms
            got.append(pt)
            print(f"  [{i:3d}/{len(POINTNAMES)}] {pt:<14s} {y.size} pts")
        h5.attrs["channels_fetched"] = np.array(got, dtype="S")
        h5.attrs["channels_missing"] = np.array(missing, dtype="S")

    print(f"\nSaved {len(got)} channels to {out}  ({len(missing)} missing)")
    if missing:
        print("Missing:", ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
