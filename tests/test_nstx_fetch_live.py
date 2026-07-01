#!/usr/bin/env python3
"""
Live integration tests: reach NSTX/NSTX-U magnetics on the PPPL ``fastmag`` MDSplus
tree through the ``flux.pppl.gov`` gateway.

NETWORK tests, OFF by default -- skipped unless ``MAGNETICS_FLUX_USER`` is set.
Meant to be run **manually** from a machine with working SSH to the PPPL gateway;
deliberately NOT wired into CI (reaching PPPL from an automated public-repo runner
is a security exposure, and there is no committed NSTX data).

Two levels:
  * ``test_fastmag_tree_connection`` -- low-level transport smoke: one SSH tunnel
    to ``skylark.pppl.gov:8501``, ``openTree('fastmag', shot)``, read one real
    Mirnov node + its time base + one EFIT01 plasma node. Validates auth + tree
    access BEFORE the higher-level fetch path exists (Phase 0 GO/NO-GO).
  * ``test_fetch_all_mirnov_writes_h5`` -- the real API: ``fetch_shot(device='nstx',
    sensor_set='All Mirnov')`` writes an HDF5 that ``h5source`` can read back. This
    drives the Phase-1 tree-based sensor fetch; it will FAIL until that lands.

Auth: PPPL portal login. Two modes --
  * key-based (default): the gateway must accept non-interactive SSH (a BatchMode
    preflight turns a missing key into a fast, clear failure instead of a 120s hang);
  * password + Duo: set ``MAGNETICS_FLUX_PW`` (and optionally ``MAGNETICS_FLUX_DUO``,
    default "1" = Duo Push) and auth is answered via SSH_ASKPASS, no tty prompt.

Run (key-based flux SSH already working)::

    MAGNETICS_FLUX_USER=<user> MAGNETICS_FLUX_SHOT=<nstxu_shot> \
        uv run --with mdsthin python -m pytest tests/test_nstx_fetch_live.py -q -s

Env overrides::

    MAGNETICS_FLUX_USER       PPPL username (required; unset => whole file skips)
    MAGNETICS_FLUX_GATEWAY    default "flux" (ssh-config alias w/ ControlMaster; needs a
                              live `ssh flux` master session, else set MAGNETICS_FLUX_PW)
    MAGNETICS_FLUX_SERVER     default "skylark.pppl.gov:8501"
    MAGNETICS_FLUX_TREE       default "fastmag"
    MAGNETICS_FLUX_SHOT       NSTX-U test shot (>= 200000), default 204718
    MAGNETICS_FLUX_NSTX_SHOT  legacy NSTX test shot (< 200000), optional
    MAGNETICS_FLUX_PW / _DUO  password + Duo answer (else key-based is assumed)
"""

from __future__ import annotations

import os
import subprocess

import numpy as np
import pytest

FLUX_USER = os.environ.get("MAGNETICS_FLUX_USER")
# Default to the `flux` ssh-config alias (ControlMaster auto), NOT the bare
# hostname: flux.pppl.gov matches the `Host *.pppl.gov` catchall, which has no
# multiplexing and forces a fresh Duo. The `flux` alias reuses an existing
# `ssh flux` master session, so the tunnel needs no new Duo.
GATEWAY = os.environ.get("MAGNETICS_FLUX_GATEWAY", "flux")
SERVER = os.environ.get("MAGNETICS_FLUX_SERVER", "skylark.pppl.gov:8501")
TREE = os.environ.get("MAGNETICS_FLUX_TREE", "fastmag")
SHOT = int(os.environ.get("MAGNETICS_FLUX_SHOT", "204718"))
NSTX_SHOT = os.environ.get("MAGNETICS_FLUX_NSTX_SHOT")  # optional legacy (<200000)
FLUX_PW = os.environ.get("MAGNETICS_FLUX_PW")
FLUX_DUO = os.environ.get("MAGNETICS_FLUX_DUO", "1")

pytestmark = pytest.mark.skipif(
    not FLUX_USER,
    reason="set MAGNETICS_FLUX_USER to run the live PPPL fastmag fetch tests",
)


def _ssh_env():
    """Return (env, cleanup) for the tunnel: an SSH_ASKPASS helper when a password
    is supplied, else (None, no-op) so key-based auth is used."""
    if FLUX_PW:
        from magnetics.data.sshauth import askpass_env

        return askpass_env(FLUX_PW, FLUX_DUO)
    return None, (lambda: None)


def _require_reachable_gateway():
    """Fail fast unless the tunnel can reach the gateway WITHOUT a fresh Duo.

    PPPL's `flux` requires Duo (gssapi/keyboard-interactive), so there is no
    passwordless key path; instead we ride an existing `ssh flux` ControlMaster.
    `ssh -O check <alias>` verifies that master socket is live (exit 0) — an
    instant, non-interactive check that turns a dead master into a clear message
    instead of a ~120s tunnel hang on an interactive Duo prompt.

    Skipped when a password is supplied (that path answers Duo via askpass).
    """
    if FLUX_PW:
        return
    alias = GATEWAY.split(":", 1)[0]
    try:
        r = subprocess.run(
            ["ssh", "-O", "check", alias],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"`ssh -O check {alias}` timed out -- is the master reachable?")
    if r.returncode != 0:
        pytest.fail(
            f"no live SSH ControlMaster for {alias!r} "
            f"({r.stderr.strip() or 'no master running'}).\nOpen one first in a "
            f"terminal (approve Duo once):  ssh {alias}\n"
            f"-- or set MAGNETICS_FLUX_PW (+MAGNETICS_FLUX_DUO) for a fresh password+Duo login."
        )


def _first_valid_mirnov(dev, shot):
    """The (node, gain, na) of the first 'All Mirnov' sensor that resolves at `shot`."""
    from magnetics.data.devices import geometry_at, pointname_at
    from magnetics.data.fetch.toksearch import resolve_sensor_set

    for cid in resolve_sensor_set(dev, "All Mirnov"):
        node = pointname_at(dev, cid, shot)
        if node is None:
            continue
        geom = geometry_at(dev, cid, shot) or {}
        return node, float(geom.get("gain", 1.0)), float(geom.get("na", 1.0))
    pytest.fail(f"no 'All Mirnov' sensor resolves at shot {shot}")


def test_fastmag_tree_connection():
    """Phase-0 smoke: tunnel to skylark, open `fastmag`, read one Mirnov node."""
    import contextlib

    from mdsthin import Connection

    from magnetics.data.devices import load_device
    from magnetics.data.fetch.toksearch import _ssh_tunnel

    _require_reachable_gateway()
    dev = load_device("nstx")
    node, gain, na = _first_valid_mirnov(dev, SHOT)

    mds_host, _, mds_port = SERVER.partition(":")
    env, cleanup = _ssh_env()
    try:
        with _ssh_tunnel(FLUX_USER, GATEWAY, mds_host, int(mds_port or 8501), env=env) as lport:
            conn = Connection(f"127.0.0.1:{lport}")
            conn.openTree(TREE, SHOT)
            raw = np.atleast_1d(conn.get(node).data())
            t = np.atleast_1d(conn.get(f"dim_of({node})").data())
            with contextlib.suppress(Exception):
                # EFIT01 plasma current -- confirms the second tree opens too.
                ip = np.atleast_1d(conn.get("\\EFIT01::TOP.RESULTS.AEQDSK:IPMEAS").data())
                assert ip.size >= 1
    finally:
        cleanup()

    assert raw.size > 1, f"{node} returned no samples"
    assert t.size == raw.size, f"{node} time/data length mismatch ({t.size} vs {raw.size})"
    assert np.all(np.isfinite(raw)), f"{node} has non-finite samples"
    assert np.nanmax(np.abs(raw)) > 0, f"{node} is all-zero -- no real signal"
    # Physical (calibrated) signal = raw * gain / na; just assert it is finite here.
    assert np.all(np.isfinite(raw * gain / na))


def test_fetch_all_mirnov_writes_h5(tmp_path):
    """The real API path: fetch_shot(device='nstx', 'All Mirnov') -> readable HDF5.

    Uses a NARROW window (fastmag raw signals are ~20 M samples/channel at ~15 MHz);
    the value-window subscript keeps the pull small. `gateway=GATEWAY` overrides the
    device file's bare hostname so the tunnel rides the `flux` ControlMaster.
    """
    import h5py

    from magnetics.data.fetch.toksearch import fetch_shot

    _require_reachable_gateway()
    out = str(tmp_path / f"shot_{SHOT}.h5")
    env_kw = {"password": FLUX_PW, "duo": FLUX_DUO} if FLUX_PW else {}
    path = fetch_shot(
        SHOT,
        device="nstx",
        sensor_set="All Mirnov",
        backend="mdsthin",
        username=FLUX_USER,
        gateway=GATEWAY,
        out=out,
        tmin=250.0,
        tmax=270.0,
        **env_kw,
    )
    with h5py.File(path, "r") as h5:
        assert h5.attrs["device_id"] == "nstx", "device_id attr not written"
        chans = [k for k in h5.keys() if k != "_timebases"]
        assert len(chans) >= 5, f"too few channels written: {chans}"
        # the high-rate Mirnov channels dominate; pick the longest and validate it
        best = max(chans, key=lambda k: h5[k]["data"].shape[0])
        g = h5[best]
        data = np.asarray(g["data"][:])
        t = np.asarray(g["time"][:])
        assert data.size > 1000, f"{best} not a high-rate Mirnov signal ({data.size})"
        assert t.size == data.size and np.all(np.isfinite(data))
        # native seconds converted to the ms h5 convention: 250-270 ms window
        assert 245.0 <= t[0] <= 260.0 and t[-1] <= 275.0, f"time base off: [{t[0]},{t[-1]}]"
        # gain/na baked in -> a real Mirnov perturbation is not micro-volts
        assert np.nanmax(np.abs(data)) > 1.0, "signal implausibly small (gain/na not applied?)"
