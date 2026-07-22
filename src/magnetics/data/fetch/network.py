#!/usr/bin/env python3
"""Where a device's data lives, and how many SSH hops it takes to reach it.

The connection endpoints are structured fields in the device file's ``network``
block -- the single source of truth, so neither the CLI user nor the GUI needs a
``~/.ssh/config`` alias or hand-passed host/jump flags:

    "network": {
      "domain":  "gat.com",
      "jump":    { "host": "cybele.gat.com", "port": 2039 },
      "mdsip":   { "host": "atlas.gat.com",  "port": 8000 },
      "cluster": { "host": "omega.gat.com",  "port": 22, "python": "…" }
    }

- ``jump``    — the site SSH gateway used off-site (mdsip tunnel + cluster ProxyJump).
- ``mdsip``   — the MDSplus data server the mdsthin backend reads.
- ``cluster`` — the compute host the ``remote`` backend runs the toksearch pull on.

Each endpoint may also carry ``"duo": true|false`` noting whether reaching it needs
an interactive 2FA (Duo/SecurID) passcode -- DIII-D (key-based through cybele) is
``false``; absent is treated as ``true`` (assume it's needed, so the UI still
prompts). See ``needs_duo``.

``on_site_network`` decides the hop count automatically: on a host inside the site
domain (``*.gat.com`` for DIII-D, ``*.pppl.gov`` for NSTX) the data hosts are
directly reachable, so we skip the gateway entirely; off-site we route through it.
This keeps the whole thing out of the user's periphery -- no flags, no ssh-config.

Legacy flat ``gateway``/``server`` string keys are still honored as a fallback so
device files that predate the ``network`` block keep working.
"""

from __future__ import annotations

import os
import socket

from ..devices import load_device


def _network(device: str) -> dict:
    """The device's ``network`` block ({} if absent or the file won't load)."""
    try:
        return load_device(device).get("network", {}) or {}
    except Exception:
        return {}


def on_site_network(device: str) -> bool:
    """True when we appear to be running INSIDE the device's site network, so its
    data hosts are directly reachable and no SSH gateway hop is needed.

    Fast and probe-free: site hosts (omega/cybele/atlas, or the PPPL cluster) carry
    an FQDN under the device's ``network.domain``; a laptop off-site does not. The
    ``MAGNETICS_ON_NETWORK`` env var (``0``/``1``) forces the answer for the rare
    misdetect -- e.g. a split-tunnel VPN that hands out a site search domain with no
    actual route to the hosts. With no configured domain we assume off-site (the
    safe default: route through the gateway).
    """
    override = os.environ.get("MAGNETICS_ON_NETWORK")
    if override is not None:
        return override.strip().lower() not in ("", "0", "false", "no")
    domain = str(_network(device).get("domain", "")).strip().lower()
    if not domain:
        return False
    return socket.getfqdn().lower().endswith(domain)


def on_cluster_host(device: str) -> bool:
    """True when THIS process is already running on the device's compute cluster,
    so the ``remote`` backend's SSH round trip would dial the very host it is
    running on.

    That self-SSH is not merely wasteful: on a node whose ``known_hosts`` lacks
    the cluster's own entry, ssh stops at the host-key confirmation prompt, and a
    server process has no terminal to answer it -- the pull hangs at 0% forever
    rather than failing. Callers use this to fetch in-process instead.

    Cluster submit nodes are load-balanced, so the FQDN we land on
    (``omega-a.gat.com``) is rarely the configured cluster address
    (``omega.gat.com``); we compare short names by prefix, gated on already being
    inside the site domain. ``MAGNETICS_ON_CLUSTER`` (``0``/``1``) forces it.
    """
    override = os.environ.get("MAGNETICS_ON_CLUSTER")
    if override is not None:
        return override.strip().lower() not in ("", "0", "false", "no")
    host = str(cluster_login(device).get("host") or "").strip().lower()
    if not host or not on_site_network(device):
        return False
    cluster_short = host.split(".")[0]
    me_short = socket.getfqdn().lower().split(".")[0]
    if not cluster_short or not me_short:
        return False
    return me_short.startswith(cluster_short)


def _hostport(block, default_port: int) -> str | None:
    """Render a ``{host, port}`` sub-block as ``host:port`` (None if no host)."""
    block = block or {}
    host = block.get("host")
    if not host:
        return None
    return f"{host}:{block.get('port', default_port)}"


def mdsip_address(device: str) -> str | None:
    """The mdsip data server as ``host:port`` (e.g. ``atlas.gat.com:8000``).

    Falls back to the legacy flat ``server`` string for pre-``network`` device files.
    """
    net = _network(device)
    addr = _hostport(net.get("mdsip"), 8000)
    if addr:
        return addr
    try:
        return load_device(device).get("server")
    except Exception:
        return None


def gateway_address(device: str) -> str | None:
    """The site SSH gateway as ``host:port`` (e.g. ``cybele.gat.com:2039``).

    Falls back to the legacy flat ``gateway`` string for pre-``network`` device files.
    """
    net = _network(device)
    addr = _hostport(net.get("jump"), 22)
    if addr:
        return addr
    try:
        return load_device(device).get("gateway")
    except Exception:
        return None


def needs_duo(device: str, which: str = "jump") -> bool:
    """Whether reaching the given endpoint (``jump`` / ``mdsip`` / ``cluster``)
    needs an interactive 2FA (Duo/SecurID) passcode, per the device file's per-url
    ``duo`` flag. Absent → True (conservative: assume it's needed so callers still
    prompt). Defaults to the ``jump`` gateway, which is the off-site auth point."""
    return bool((_network(device).get(which, {}) or {}).get("duo", True))


def cluster_login(device: str) -> dict:
    """The ``remote`` backend's cluster login: ``{host, port, python}`` (values may
    be None when the device omits a ``cluster`` block)."""
    c = _network(device).get("cluster", {}) or {}
    return {
        "host": c.get("host"),
        "port": int(c.get("port", 22)),
        "python": c.get("python"),
    }
