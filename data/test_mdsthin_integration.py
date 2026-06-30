#!/usr/bin/env python3
"""
Live integration test: fetch a few real DIII-D pointnames through the GA gateway.

This is a NETWORK test and is OFF by default -- it is skipped unless
``MAGNETICS_GA_USER`` is set. It is meant to be run **manually**, from a machine
that already has working (key-based, no-Duo) SSH to the GA gateway; it is
deliberately NOT wired into CI, since reaching the GA cluster from an automated
runner on a public repo is a security exposure. It exercises the real mdsthin
remote path -- one SSH tunnel through the gateway + mdsip fetch -- on a tiny
signal subset so it stays fast (the full per-analysis pull is ~170 channels).

The gateway is reached via an ssh-config Host alias (default ``cybele``) so the
gateway's non-standard SSH port and identity come from your ``~/.ssh/config``.

It calls ``toksearch_fetch._fetch_mdsthin`` directly with a 3-pointname list
rather than ``fetch_shot`` so the test is a quick smoke of the transport, not a
full shot download.

Run locally (needs key-based SSH to the gateway alias already working):
    MAGNETICS_GA_USER=<user> uv run --with mdsthin,h5py,numpy,pytest \
        python -m pytest data/test_mdsthin_integration.py -q -s

Override the gateway alias / server / shot via env:
    MAGNETICS_GA_GATEWAY (default "cybele" -- an ssh-config Host carrying the port)
    MAGNETICS_GA_SERVER  (default "atlas.gat.com:8000")
    MAGNETICS_GA_SHOT    (default 184927)
"""
from __future__ import annotations

import os
import queue
import subprocess

import numpy as np
import pytest

GA_USER = os.environ.get("MAGNETICS_GA_USER")
# Gateway is an ssh-config Host alias so the (non-22) port + identity come from
# ~/.ssh/config; a laptop already has it.
GATEWAY = os.environ.get("MAGNETICS_GA_GATEWAY", "cybele")
SERVER = os.environ.get("MAGNETICS_GA_SERVER", "atlas.gat.com:8000")
SHOT = int(os.environ.get("MAGNETICS_GA_SHOT", "184927"))

pytestmark = pytest.mark.skipif(
    not GA_USER,
    reason="set MAGNETICS_GA_USER to run the live GA mdsthin fetch test",
)


def _require_passwordless_gateway():
    """Fail fast (and clearly) unless the gateway accepts non-interactive auth.

    The fetch tunnel runs `ssh` without BatchMode, so a host that still wants a
    password/Duo would drop to an interactive prompt and hang for ~120s before
    erroring. This preflight does the same login WITH BatchMode so a missing
    `ssh-copy-id` turns into an immediate, actionable failure instead.
    """
    target = f"{GA_USER}@{GATEWAY}"
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
             "-o", "StrictHostKeyChecking=accept-new", target, "true"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"SSH to gateway {target!r} timed out — is it reachable on its "
            "configured port (and is this machine allowed through GA's firewall)?"
        )
    if r.returncode != 0:
        pytest.fail(
            f"non-interactive SSH to gateway {target!r} failed "
            f"(exit {r.returncode}): {r.stderr.strip() or 'no stderr'}\n"
            "The fetch tunnel cannot answer a password/Duo prompt. Set up "
            "key-based login first, e.g.:  ssh-copy-id "
            f"{target}  (and ensure the gateway alias carries the right host/port "
            "in ~/.ssh/config), so login needs no password or Duo."
        )


def test_fetch_real_pointnames_through_gateway():
    """Pull a handful of real pointnames and assert physical data came back."""
    from toksearch_fetch import _fetch_mdsthin

    # Turn a missing ssh-copy-id into a fast, clear failure (not a 120s hang).
    _require_passwordless_gateway()


    pts = ["ip", "bt", "MPID66M067"]
    # _fetch_mdsthin now streams completed batches to a sink (a queue) and returns
    # None; with no concurrent writer an unbounded queue just buffers them, so drain
    # it after the fetch returns to collect the channels this smoke test asserts on.
    sink: queue.Queue = queue.Queue()
    _fetch_mdsthin(
        SHOT, pts,
        username=GA_USER, gateway=GATEWAY, server=SERVER, tcp=False,
        tmin=2000.0, tmax=3000.0, stride=8,
        workers=2, batch_size=10, progress=lambda frac, msg: None,
        sink=sink,
    )
    channels = []
    while not sink.empty():
        channels.extend(sink.get())

    by_name = {c.name: c for c in channels}
    fetched = [c for c in channels if c.ok]

    # If the tunnel/auth/mdsip path failed we get zero channels back.
    assert fetched, (
        "no channels fetched -- the gateway/auth/mdsip path failed; "
        f"errors: {[(c.name, c.error) for c in channels]}"
    )

    # ip is always present on a real DIII-D shot; check it is physical.
    ip = by_name["ip"]
    assert ip.ok, f"ip not fetched: {ip.error}"
    assert ip.data.size > 1, "ip came back with no samples"
    assert ip.time.size == ip.data.size, "ip time/data length mismatch"
    assert np.all(np.isfinite(ip.data)), "ip has non-finite samples"
    # DIII-D plasma current is ~10^5--10^6 A; a flat/zero array means no real data.
    assert np.nanmax(np.abs(ip.data)) > 1e4, "ip amplitude implausibly small"

    # The requested server-side window was honored (ms).
    assert ip.time.min() >= 1990.0 and ip.time.max() <= 3010.0
