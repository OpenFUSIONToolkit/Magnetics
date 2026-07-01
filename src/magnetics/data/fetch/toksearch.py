#!/usr/bin/env python3
"""
Fast, analysis-aware DIII-D magnetics fetcher -> HDF5.

Pulls the PTDATA pointnames used by the OMFIT `magnetics` module for a shot,
*downselected by analysis type* (quasi-stationary / rotating / both), and writes
one compact HDF5 file per shot. Built for speed (CLAUDE.md: "Speed is paramount").

Two interchangeable backends, chosen by `--backend`:

  * toksearch (default on the GA cluster): builds a `toksearch.Pipeline` over the
    shot(s) and fetches with `PtDataSignal`. PTDATA is local on the cluster, so
    this is the fast path; passing several shots parallelizes across them for free
    (`compute_ray` / `compute_multiprocessing`).

  * mdsthin (laptop / off-cluster): pure-Python MDSplus thin client reaching
    atlas through the cybele SSH gateway (`sshp://`), exactly like
    data/pull_shot_h5.py -- but parallelized across a pool of connections so the
    many channels are pulled concurrently instead of one-at-a-time.

Speed levers, in order of impact:
  1. run where the data is (toksearch on the cluster -> no network round trips);
  2. move less data: downselect signals by analysis + per-analysis server-side
     time-window trim and (quasi-stationary only) decimation;
  3. parallelism: across shots (toksearch) or across channels (mdsthin pool);
  4. fast serialization: chunked HDF5 with `lzf`, float32, deduped time bases.

Neither toksearch nor mdsthin is a project dependency (toksearch will not install
on the repo's Python 3.14). Run this under the cluster's toksearch environment, or
locally via:  uv run --with mdsthin,h5py,numpy python data/toksearch_fetch.py ...

Usage:
    # cluster, toksearch, rotating-mode signals only, full rate
    python data/toksearch_fetch.py --shot 184927 --analysis rotating

    # laptop, mdsthin through the gateway, quasi-stationary, trimmed + decimated
    uv run --with mdsthin,h5py,numpy python data/toksearch_fetch.py \
        --backend mdsthin --shot 184927 --analysis quasi-stationary \
        --tmin 2000 --tmax 3000 --decimate 4
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import numpy as np

from .. import h5source
from .. import signals as ms

# Shared device config + shot-aware geometry resolution (one impl for fetch +
# analysis). `load_device` is the single source of truth for a machine's mdsip
# addresses/geometry; `pointname_at` maps a canonical sensor id → the pointname
# valid at a shot (None = out of range / decommissioned).
from ..devices import load_device, pointname_at, segment_at

# Connection endpoints (mdsip / gateway) + automatic on-site detection, resolved
# from the device file's `network` block so the hop count is picked for the user.
from .network import gateway_address, mdsip_address, on_site_network

# All fetched shot files land in the runtime data dir (data/datafile/) — the same
# place h5source reads back from ($MAGNETICS_DATA_DIR or the repo's data/ dir).
DATA_DIR = h5source.data_dir() / "datafile"


def _resolve_pointnames(dev, pointnames, shot):
    """Map canonical sensor ids -> the MDS pointnames valid at `shot`.

    Returns ``(query_pointnames, canonical_of, skipped)``:
      * ``query_pointnames`` — the names to actually fetch (a legacy/alternate
        pointname for an old shot, else the canonical id), out-of-range and
        decommissioned (``NotAvailable``) sensors dropped;
      * ``canonical_of`` — ``{queried pointname -> canonical sensor id}`` so the
        writer can relabel groups back to the shot-agnostic id;
      * ``skipped`` — canonical ids with no valid segment at this shot.
    Names the device file doesn't model (plasma ip/bt/kappa) pass through unchanged.
    """
    sensors_cfg = dev.get("sensors", {})
    shot_i = int(shot)
    query: list[str] = []
    canonical_of: dict[str, str] = {}
    skipped: list[str] = []
    for cid in pointnames:
        if cid not in sensors_cfg:  # unmodeled (plasma params, etc.)
            query.append(cid)
            canonical_of[cid] = cid
            continue
        pt = pointname_at(dev, cid, shot_i)
        if pt is None:  # out of range / NotAvailable
            skipped.append(cid)
            continue
        query.append(pt)
        canonical_of[pt] = cid
    return query, canonical_of, skipped


def _plasma_signal(entry):
    """Parse a device "plasma pointnames" entry -> (name, tree_candidates).

    An entry is ``{"name": <pt>, "tree": <tree?>, "node": <node?>}`` (a bare
    string is tolerated as a legacy `{"name": str}`). If a "tree" is given the
    quantity lives in an MDSplus tree, so we return ordered (tree, node)
    candidates for the tree-fetch path; the node defaults to ``\\<name>`` (with
    the AEQDSK results path as a fallback), or an explicit "node" is used as-is.
    With no "tree", `tree_candidates` is empty and `name` is a PTDATA pointname.
    """
    if isinstance(entry, str):
        return entry, []
    name = entry["name"]
    tree = entry.get("tree")
    if not tree:
        return name, []
    node = entry.get("node")
    if node:
        return name, [(tree, node)]
    bare = name if name.startswith("\\") else "\\" + name
    return name, [(tree, bare), (tree, r"\top.results.aeqdsk:" + name.lstrip("\\"))]


def _dedup(names):
    """Order-preserving de-duplication of a pointname list."""
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def resolve_sensor_set(dev: dict, name: str, _seen=None) -> list[str]:
    """Flatten a device sensor set (data/device/<device>.json "sensor_sets") to
    a deduplicated, ordered pointname list.

    A set is either ``{"type": "list", "sensors": [...]}`` or a composite
    ``{"type": "composite", "sets": [<other set names>]}`` that is expanded
    recursively. Raises ValueError on an unknown set, an unknown type, or a
    circular composite reference.
    """
    sets = dev.get("sensor_sets", {})
    if name not in sets:
        avail = ", ".join(sets) or "none"
        raise ValueError(f"unknown sensor set {name!r}; available: {avail}")
    _seen = set() if _seen is None else _seen
    if name in _seen:
        raise ValueError(f"circular sensor-set reference at {name!r}")
    _seen.add(name)

    spec = sets[name]
    kind = spec.get("type")
    out: list[str] = []
    if kind == "list":
        out.extend(spec.get("sensors", []))
    elif kind == "composite":
        for sub in spec.get("sets", []):
            out.extend(resolve_sensor_set(dev, sub, _seen))
    else:
        raise ValueError(f"sensor set {name!r} has unknown type {kind!r}")
    return _dedup(out)


# A progress callback: (fraction_done in [0,1], human message) -> None.
Progress = Callable[[float, str], None]


def _default_progress(frac: float, msg: str) -> None:
    """Single-line stderr progress bar (keeps the user informed during a pull)."""
    width = 28
    filled = int(width * frac)
    bar = "#" * filled + "-" * (width - filled)
    sys.stderr.write(f"\r[{bar}] {frac * 100:5.1f}%  {msg:<32.32s}")
    sys.stderr.flush()
    if frac >= 1.0:
        sys.stderr.write("\n")


# --- channel record -----------------------------------------------------------
class Channel:
    """One fetched pointname: time (ms, float64) + data (float32)."""

    __slots__ = ("name", "time", "data", "ok", "error")

    def __init__(self, name, time=None, data=None, ok=False, error=""):
        self.name = name
        self.time = time
        self.data = data
        self.ok = ok
        self.error = error


def _reduce(t: np.ndarray, y: np.ndarray, tmin, tmax, stride: int):
    """Client-side window + decimate fallback (used after a full fetch)."""
    if tmin is not None or tmax is not None:
        lo = -np.inf if tmin is None else tmin
        hi = np.inf if tmax is None else tmax
        sel = (t >= lo) & (t <= hi)
        t, y = t[sel], y[sel]
    if stride > 1:
        t, y = t[::stride], y[::stride]
    return t, y


@contextlib.contextmanager
def _ssh_tunnel(username, gateway, mds_host, mds_port, env=None):
    """Open ONE authenticated SSH local-forward to the mdsip server.

    Off-cluster, parallel mdsip needs parallelism WITHOUT N separate logins: with
    2FA/Duo you can only authenticate once. So we forward a local port through the
    gateway to the mdsip host a single time (one password + Duo prompt), and every
    worker then opens a plain-TCP mdsip connection to 127.0.0.1:<lport>,
    multiplexed over the one ssh connection.

    Yields the local port. If `env` carries an SSH_ASKPASS helper (GUI-supplied
    credentials), auth is answered without a terminal prompt; otherwise ssh prompts
    on the tty. Torn down on exit.
    """
    # grab a free local port
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    lport = s.getsockname()[1]
    s.close()

    # `gateway` may be a real host, a host:port (GA's cybele listens on 2039), or
    # an ~/.ssh/config Host alias. Parse an optional :port so we don't depend on an
    # ssh-config alias; only prepend user@ when an explicit --username is given.
    gw_host, _, gw_port = gateway.partition(":")
    target = f"{username}@{gw_host}" if username else gw_host
    # -C (SSH compression): mdsip ships raw float, but PTDATA waveforms are ~4-5x
    # compressible, and this laptop->cybele->atlas tunnel is the slow off-network
    # path (the --tcp on-network path bypasses this function). Measured ~-26% wall
    # time on a 374 MB rotating pull (80.8s -> 59.8s); zlib CPU is well worth it on
    # a few-MB/s link. Harmless: it only narrows the win if the link is ever fast.
    cmd = ["ssh", "-C", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30", "-N"]
    if gw_port:
        cmd += ["-p", gw_port]
    cmd += ["-L", f"{lport}:{mds_host}:{mds_port}", target]
    prompt = (
        "(using supplied credentials; approve Duo if pushed)"
        if env
        else "(your terminal will prompt for password + Duo once)"
    )
    sys.stderr.write(
        f"Opening one SSH tunnel via {gateway} -> {mds_host}:{mds_port} "
        f"(local :{lport}).\n{prompt}\n"
    )
    proc = subprocess.Popen(cmd, env=env)  # env may carry SSH_ASKPASS
    try:
        ready = False
        for _ in range(1200):  # up to ~120s to complete Duo + open the forward
            if proc.poll() is not None:
                raise SystemExit(
                    "SSH tunnel exited before it was ready (auth failed or forward refused)."
                )
            with socket.socket() as probe:
                probe.settimeout(0.5)
                if probe.connect_ex(("127.0.0.1", lport)) == 0:
                    ready = True
                    break
            time.sleep(0.1)
        if not ready:
            raise SystemExit("SSH tunnel did not become ready in time.")
        yield lport
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


# --- mdsthin backend (laptop / remote, parallel across channels) --------------
def _mdsthin_tree_channels(connect, shot, tree_signals, tmin, tmax, progress):
    """Fetch EFIT-tree signals on one connection (openTree + node).

    `tree_signals` is {name: [(tree, node), ...]}; for each name the candidates
    are tried in order and the first that opens and returns a usable (data, time)
    pair wins. These are equilibrium quantities (e.g. elongation) that are not in
    PTDATA, so they bypass the ptdata2 channel pool. The window (tmin/tmax) is
    applied client-side; no decimation -- EFIT time bases are already coarse.
    """
    out: list[Channel] = []
    if not tree_signals:
        return out
    conn = connect()
    for name, candidates in tree_signals.items():
        ch = Channel(name, ok=False, error="no data")
        for tree, node in candidates:
            try:
                conn.openTree(tree, shot)
            except Exception as exc:
                ch.error = f"open {tree}: {exc}"
                continue
            try:
                y = np.atleast_1d(conn.get(node).data())
                t = np.atleast_1d(conn.get(f"dim_of({node})").data())
                if y.size >= 1 and t.size == y.size and np.all(np.isfinite(t)):
                    t, y = _reduce(t, y, tmin, tmax, 1)
                    ch = Channel(
                        name,
                        t.astype(np.float64, copy=False),
                        y.astype(np.float32, copy=False),
                        ok=True,
                    )
                    break
                ch.error = f"{tree}{node}: degenerate (n={y.size}, t={t.size})"
            except Exception as exc:
                ch.error = f"{tree}{node}: {exc}"
        out.append(ch)
        progress(1.0, f"tree:{name} ({'ok' if ch.ok else 'missing'})")
    return out


def _fetch_mdsthin(
    shot,
    pointnames,
    *,
    username,
    gateway,
    server,
    tcp,
    tmin,
    tmax,
    stride,
    workers,
    batch_size,
    progress,
    tree_signals=None,
    ssh_env=None,
    per_channel=False,
):
    """Pull pointnames concurrently over a pool of mdsthin connections.

    Each worker owns its own connection (mdsthin Connections are not thread-safe
    to share) and pulls a slice of the channel list. PTDATA fetches are
    server-I/O bound, so N connections give a near-linear speedup over the
    sequential one-connection loop in pull_shot_h5.py.

    Off-cluster (the default, not --tcp) all workers share ONE SSH tunnel so there
    is a single password/Duo prompt; on-network (--tcp) each worker connects to
    mdsip directly. Reduction (window + stride) is pushed server-side via a TDI
    subscript so only the reduced samples cross the wire.

    By default each worker tries `getMany` (one round trip per batch) and only
    drops to the per-channel path if that fails. `per_channel=True` skips the
    batch attempt entirely and fetches one pointname at a time from the start --
    for servers where getMany reliably fails, this avoids the wasted first-batch
    round trip (and its stderr warning) per worker.
    """
    try:
        from mdsthin import Connection
    except ImportError:
        sys.exit("Missing dependency: pip/uv install mdsthin  (pure-python MDSplus thin client)")

    mds = server.split("://", 1)[-1].split("@", 1)[-1]
    mds_host, _, mds_port = mds.partition(":")
    mds_port = int(mds_port or 8000)

    # The link is latency-bound, not bandwidth-bound: over the laptop->cybele->
    # atlas double hop, wall-clock is dominated by the NUMBER of round trips. So we
    # batch many channels into a single `getMany().execute()` -- one round trip per
    # batch instead of two per channel (~344 -> a handful for a 172-channel pull).
    #
    # The server-side reduction is the suffix appended to ptdata2: a signal slices
    # by its dimension's units for a value window, by index for a strided range, and
    # dim_of() recovers the matching time axis. Pointname + shot go in as `$`
    # placeholders (bound to descriptors) so nothing is string-injected.
    def _reduce_suffix():
        sfx = ""
        if tmin is not None or tmax is not None:
            lo = "*" if tmin is None else repr(float(tmin))
            hi = "*" if tmax is None else repr(float(tmax))
            sfx += f"[{lo} : {hi}]"
        if stride > 1:
            sfx += f"[0 : * : {stride}]"
        return sfx

    suffix = _reduce_suffix()
    data_expr = f"(ptdata2($, $)){suffix}"  # $1=pointname, $2=shot
    time_expr = f"dim_of((ptdata2($, $)){suffix})"

    def _arr(x):
        # getMany values and conn.get() results are Descriptors -> ndarray
        return np.atleast_1d(x.data() if hasattr(x, "data") else np.asarray(x))

    def _good(arr):
        # ptdata2 returns a length-1 [0] when a pointname has no data
        return not (arr.size <= 1 and (arr.size == 0 or arr[0] == 0))

    n = len(pointnames)

    # Split channels into batches; spread batches across a small pool of
    # connections (each connection runs its batches serially, one round trip each).
    batch_size = max(1, batch_size)
    batches = [pointnames[i : i + batch_size] for i in range(0, n, batch_size)]
    workers = max(1, min(workers, len(batches)))

    import threading

    lock = threading.Lock()
    state = {"done": 0}

    def tick(name, k=1):
        with lock:
            state["done"] += k
            frac = state["done"] / n
        progress(frac, name)

    def fetch_one(conn, pt):  # per-channel fallback (2 round trips)
        data = np.atleast_1d(conn.get(f"_s = {data_expr}", pt, shot).data())
        if not _good(data):
            return None, None, False
        t = np.atleast_1d(conn.get("dim_of(_s)").data())
        return t, data, True

    def fetch_batch(conn, batch, use_many):
        """Return (list[Channel], use_many) for one batch.

        Tries getMany (one round trip); on failure flips to the per-channel path
        for the rest of the run.
        """
        out: list[Channel] = []
        if use_many:
            try:
                gm = conn.getMany()
                for i, pt in enumerate(batch):
                    gm.append(f"d{i}", data_expr, pt, shot)
                    gm.append(f"t{i}", time_expr, pt, shot)
                gm.execute()
                for i, pt in enumerate(batch):
                    try:
                        y = _arr(gm.get(f"d{i}"))  # raises if this channel errored
                        if not _good(y):
                            out.append(Channel(pt, ok=False, error="no data"))
                            continue
                        t = _arr(gm.get(f"t{i}"))
                        out.append(Channel(pt, t, y.astype(np.float32, copy=False), ok=True))
                    except Exception as exc:  # per-channel error in the batch
                        out.append(Channel(pt, ok=False, error=str(exc)))
                tick(batch[-1], k=len(batch))
                return out, True
            except Exception as exc:  # whole-batch failure -> fall back
                sys.stderr.write(f"\ngetMany unavailable ({exc}); using per-channel fetch.\n")
                use_many = False
        # per-channel fallback
        for pt in batch:
            try:
                t, y, ok = fetch_one(conn, pt)
                if ok:
                    out.append(Channel(pt, t, y.astype(np.float32, copy=False), ok=True))
                else:
                    out.append(Channel(pt, ok=False, error="no data"))
            except Exception as exc:
                out.append(Channel(pt, ok=False, error=str(exc)))
            tick(pt)
        return out, False

    def run_worker(connect, my_batches):
        conn = connect()
        use_many = not per_channel
        out: list[Channel] = []
        for batch in my_batches:
            got, use_many = fetch_batch(conn, batch, use_many)
            out.extend(got)
        return out

    def run_all(connect, label):
        progress(0.0, label)
        # round-robin batches to workers
        assigned: list[list[list[str]]] = [[] for _ in range(workers)]
        for i, b in enumerate(batches):
            assigned[i % workers].append(b)
        results: list[Channel] = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(run_worker, connect, a) for a in assigned if a]
            for fut in as_completed(futures):
                results.extend(fut.result())
        order = {pt: i for i, pt in enumerate(pointnames)}  # deterministic output
        results.sort(key=lambda c: order[c.name])
        return results

    tree_signals = tree_signals or {}

    if tcp:
        # On-network: each worker dials mdsip directly (no gateway, no auth race).
        def connect():
            return Connection(f"{username}@{mds_host}:{mds_port}")

        results = run_all(connect, f"{len(batches)} batches x{batch_size} ({workers} conns)")
        results += _mdsthin_tree_channels(connect, shot, tree_signals, tmin, tmax, progress)
        return results
    # Off-network: one SSH tunnel, then a few TCP mdsip conns through it.
    with _ssh_tunnel(username, gateway, mds_host, mds_port, env=ssh_env) as lport:

        def connect():
            return Connection(f"{username}@127.0.0.1:{lport}")

        results = run_all(connect, f"{len(batches)} batches x{batch_size} via tunnel")
        results += _mdsthin_tree_channels(connect, shot, tree_signals, tmin, tmax, progress)
        return results


# --- toksearch backend (cluster, native local PTDATA) -------------------------
# --- mds-tree device backend (KSTAR: per-signal openTree via a VPN transport) -
def _node_tree_map(dev):
    """Map each canonical sensor id -> its MDS tree, from the device's per-group
    ``signal_groups[<set>].tree`` metadata (falling back to the device-level
    ``tree``). KSTAR magnetics span several trees (Mirnov->'kstar',
    locked-mode->'MAGNETIC', ...), so a single device tree is not enough."""
    groups = dev.get("signal_groups", {})
    default_tree = dev.get("tree")
    node_tree: dict[str, str] = {}
    for set_name, spec in dev.get("sensor_sets", {}).items():
        if spec.get("type") != "list":
            continue  # composites resolve to their member lists
        tree = groups.get(set_name, {}).get("tree", default_tree)
        for node in spec.get("sensors", []):
            node_tree.setdefault(node, tree)
    return node_tree, default_tree


def _fetch_mds_tree(shot, items, *, connect, tmin, tmax, progress, resample_dt=1e-6):
    """Fetch tree nodes one-by-one over a single mdsthin connection.

    ``items`` is a list of ``(canonical_id, node, tree, gain)``: open each node's
    tree, pull data + DIM_OF(time), apply the shot-era polarity/scale ``gain`` so
    values come out physical, and key the Channel by the canonical id. The window
    (tmin/tmax, in the signal's own time units — SECONDS for KSTAR) is pushed
    SERVER-SIDE via a TDI dimension slice ``(node)[lo : hi]`` so only the windowed
    samples cross the tunnel (a full 2 MHz channel is otherwise ~10^7 points).
    Per-node failures are recorded, not fatal.

    KSTAR MDS loads the full channel to satisfy any window, so we push a server-side
    ``resample(node, tmin, tmax, dt)`` when both bounds are given: it bounds the wire
    transfer (a raw 2 MHz channel is ~10^7 pts) at a cadence far above rotating-mode
    frequencies (kHz). ``resample_dt`` seconds sets that cadence (default 1 µs =
    1 MHz). With an open/absent window it falls back to a raw dimension slice."""

    def _slice(expr):
        if tmin is None and tmax is None:
            return expr
        lo = "*" if tmin is None else repr(float(tmin))
        hi = "*" if tmax is None else repr(float(tmax))
        if tmin is not None and tmax is not None and resample_dt:
            return f"resample({expr}, {lo}, {hi}, {float(resample_dt)!r})"
        return f"({expr})[{lo} : {hi}]"

    conn = connect()
    out: list[Channel] = []
    n = len(items) or 1
    current_tree = None
    for i, (canon, node, tree, gain) in enumerate(items, 1):
        try:
            if tree != current_tree:
                conn.openTree(tree, int(shot))
                current_tree = tree
            sliced = _slice(node)
            y = np.atleast_1d(np.asarray(conn.get(sliced).data(), dtype=np.float32))
            t = np.atleast_1d(np.asarray(conn.get(f"DIM_OF({sliced})").data()))
            # Reject degenerate results (e.g. a node with no data in the window can
            # come back as a single garbage sample / non-monotonic time axis).
            if y.size < 2 or t.size != y.size or not np.all(np.isfinite(t)) or not (t[-1] > t[0]):
                out.append(Channel(canon, ok=False, error=f"degenerate result (n={y.size})"))
                progress(i / n, canon)
                continue
            if gain not in (None, 1.0):
                y = (y * np.float32(gain)).astype(np.float32, copy=False)
            # KSTAR MDS time is in SECONDS, but the h5 writer labels time_units="ms" and
            # the service nodes assume ms — scale the float time axis to ms before storing.
            t = t * 1000.0
            out.append(
                Channel(
                    canon,
                    t.astype(np.float64, copy=False),
                    y.astype(np.float32, copy=False),
                    ok=True,
                )
            )
        except Exception as exc:  # noqa: BLE001 — one bad node shouldn't sink the pull
            current_tree = None  # a failed openTree/get can leave the conn unsure
            out.append(Channel(canon, ok=False, error=str(exc)))
        progress(i / n, canon)
    return out


def _fetch_toksearch(shot, pointnames, *, tmin, tmax, stride, progress, tree_signals=None):
    """Pull pointnames for a shot via a toksearch Pipeline.

    This is the on-cluster fast path: `toksearch_d3d.PtDataSignal` reads PTDATA
    natively/locally on the node (the `ptdata` package), bypassing the mdsip TCP
    protocol the mdsthin backend pays over the wire. Benchmarked ~5-7x faster than
    `MDSplus.Connection` on omega for a full magnetics channel set.

    PtDataSignal's default `ical=1` produces values + a ms time axis byte-identical
    (after the float32 cast in the writer) to the mdsthin path's `ptdata2()` -- the
    two backends write the SAME HDF5. toksearch parallelizes across *shots*, not
    signals, so a single shot uses `compute_serial`; reduction (window/decimate) is
    applied client-side after the fetch to stay version-agnostic.

    Requires `toksearch` + the `toksearch_d3d` plugin (PtDataSignal lives in the
    plugin, not core toksearch -- core is device-agnostic and omits PTDATA).
    """
    try:
        from toksearch import Pipeline  # ty: ignore[unresolved-import]
    except ImportError:
        sys.exit(
            "Missing dependency: toksearch is not installed in this "
            "environment. Run on the GA cluster's toksearch env, or use "
            "--backend mdsthin."
        )
    try:
        from toksearch_d3d import PtDataSignal  # ty: ignore[unresolved-import]
    except ImportError:
        try:  # older/newer layouts re-export it from core toksearch
            from toksearch import PtDataSignal  # type: ignore
        except ImportError:
            sys.exit(
                "Missing dependency: toksearch_d3d (the DIII-D PTDATA plugin) "
                "is not installed. Install toksearch_d3d, or use "
                "--backend mdsthin."
            )

    tree_signals = tree_signals or {}
    # EFIT-tree signals (e.g. elongation) come from MdsSignal(node, tree), not
    # PtDataSignal. Each candidate is fetched under a temp key; we resolve to the
    # first that returns data after the pipeline runs.
    MdsSignal = None
    tree_keys: dict[str, list[tuple[str, str, str]]] = {}
    if tree_signals:
        try:
            from toksearch import MdsSignal  # type: ignore
        except ImportError:
            MdsSignal = None

    pipe = Pipeline([shot])
    for pt in pointnames:
        pipe.fetch(pt, PtDataSignal(pt))  # ical=1 default == ptdata2()
    if MdsSignal is not None:
        for name, candidates in tree_signals.items():
            keys = []
            for k, (tree, node) in enumerate(candidates):
                key = f"__tree_{name}_{k}"
                try:
                    pipe.fetch(key, MdsSignal(node, tree))
                    keys.append((key, tree, node))
                except Exception:
                    pass
            tree_keys[name] = keys

    progress(0.0, "running toksearch pipeline")
    # Single shot -> compute_serial (cross-shot parallelism is moot for one record);
    # fall back to node-local multiprocessing only if serial is somehow unavailable.
    records = None
    for runner in ("compute_serial", "compute_multiprocessing"):
        fn = getattr(pipe, runner, None)
        if fn is None:
            continue
        try:
            records = list(fn())
            break
        except Exception:
            continue
    if records is None:
        sys.exit("toksearch could not run any compute backend.")

    rec = records[0]
    # failed pointnames land in rec["errors"] (e.g. "Pointname does not exist");
    # those are the analogue of the mdsthin path's no-data channels.
    errors = rec["errors"] if "errors" in rec.keys() else {}
    n = len(pointnames)
    results: list[Channel] = []
    for i, pt in enumerate(pointnames, 1):
        sig = None if pt in errors else rec[pt]
        # a toksearch signal is a dict {n_over, n_under, data, times, units}; a
        # missing pointname is None (and/or recorded in errors above).
        if sig is None or "data" not in sig:
            err = "no data"
            if pt in errors:
                err = (
                    str(errors[pt].get("type", "no data"))
                    if hasattr(errors[pt], "get")
                    else "no data"
                )
            results.append(Channel(pt, ok=False, error=err))
        else:
            y = np.atleast_1d(np.asarray(sig["data"]))
            t = np.atleast_1d(np.asarray(sig["times"]))
            if y.size <= 1:  # degenerate -> treat as no data
                results.append(Channel(pt, ok=False, error="no data"))
            else:
                t, y = _reduce(t, y, tmin, tmax, stride)
                results.append(
                    Channel(
                        pt,
                        t.astype(np.float64, copy=False),
                        y.astype(np.float32, copy=False),
                        ok=True,
                    )
                )
        progress(i / n, pt)

    # Resolve EFIT-tree signals: first candidate key with usable data wins. No
    # decimation (EFIT time bases are already coarse), window-trim only.
    for name, keys in tree_keys.items():
        ch = Channel(name, ok=False, error="no data")
        for key, tree, node in keys:
            sig = None if key in errors else (rec[key] if key in rec.keys() else None)
            if not sig or "data" not in sig:
                continue
            y = np.atleast_1d(np.asarray(sig["data"]))
            t = np.atleast_1d(np.asarray(sig["times"]))
            if y.size >= 1 and t.size == y.size:
                t, y = _reduce(t, y, tmin, tmax, 1)
                ch = Channel(
                    name,
                    t.astype(np.float64, copy=False),
                    y.astype(np.float32, copy=False),
                    ok=True,
                )
                break
        results.append(ch)
        progress(1.0, f"tree:{name} ({'ok' if ch.ok else 'missing'})")
    return results


# --- HDF5 writer (lzf + chunked + deduped time bases) -------------------------
def _attr_names(h5, attr):
    """Read a "S"-dtype channel-name list attr back as a set of str."""
    arr = h5.attrs.get(attr)
    if arr is None:
        return set()
    return {x.decode() if isinstance(x, bytes) else str(x) for x in arr}


def _write_h5(
    path,
    shot,
    analysis,
    backend,
    channels,
    *,
    compression,
    tmin,
    tmax,
    stride,
    device="DIII-D",
    source="PTDATA via ptdata2()",
    query_names=None,
    merge=False,
):
    import h5py

    query_names = query_names or {}

    comp = None if compression in (None, "none") else compression
    missing = [c for c in channels if not c.ok]

    # A channel can fetch data samples yet come back with a degenerate time axis
    # (dim_of/times empty or None -> an object-dtype array holding None). Such a
    # channel has no usable time base, so reclassify it as missing instead of
    # crashing the writer on float(c.time[0]).
    got = []
    for c in (ch for ch in channels if ch.ok):
        t = None if c.time is None else np.asarray(c.time)
        if (
            t is None
            or t.size == 0
            or not np.issubdtype(t.dtype, np.number)
            or not np.all(np.isfinite(t))
        ):
            c.ok = False
            c.error = "no usable time axis"
            missing.append(c)
        else:
            c.time = t
            got.append(c)

    # merge -> append new channels into an existing shot file (same window +
    # decimation, already verified by the caller); else write fresh.
    append = merge and Path(path).exists()
    with h5py.File(path, "a" if append else "w") as h5:
        if not append:
            h5.attrs["shot"] = shot
            h5.attrs["device"] = device
            h5.attrs["source"] = source
            h5.attrs["analysis"] = analysis
            h5.attrs["backend"] = backend
            h5.attrs["tmin"] = "*" if tmin is None else float(tmin)
            h5.attrs["tmax"] = "*" if tmax is None else float(tmax)
            h5.attrs["decimate"] = int(stride)
        else:
            # record the added selection alongside any earlier one
            prev = h5.attrs.get("analysis")
            prev = prev.decode() if isinstance(prev, bytes) else str(prev or "")
            labels = [s for s in prev.split("+") if s]
            if analysis and analysis not in labels:
                labels.append(analysis)
            h5.attrs["analysis"] = "+".join(labels)

        # Dedup identical time bases: store each unique vector once and hard-link
        # every channel's "time" to it. inspect_h5.py still sees a per-channel
        # "time" dataset (a hard link is transparent), but we write it once. On a
        # merge we keep existing time bases and number new ones after them (we do
        # not dedup across the merge boundary -- a minor, harmless storage cost).
        tb_grp = h5.require_group("_timebases")
        tb_cache: dict[tuple, str] = {}
        tb_n = len(tb_grp)
        for c in got:
            # Content-address the time vector: identical vectors share storage,
            # but two distinct vectors that happen to share (shape, endpoints, N)
            # must NOT collide — a metadata-only key silently hard-links them and
            # corrupts the second channel's timestamps.
            key = (
                c.time.dtype.str,
                c.time.shape,
                hashlib.sha1(np.ascontiguousarray(c.time)).digest(),
            )
            tb_name = tb_cache.get(key)
            if tb_name is None:
                tb_name = f"tb{tb_n}"
                tb_n += 1
                tb_grp.create_dataset(
                    tb_name, data=c.time, compression=comp, chunks=True if comp else None
                )
                tb_grp[tb_name].attrs["time_units"] = "ms"
                tb_cache[key] = tb_name

            if c.name in h5:  # re-fetched (e.g. --force on a merge): replace
                del h5[c.name]
            g = h5.create_group(c.name)
            g.create_dataset("data", data=c.data, compression=comp, chunks=True if comp else None)
            g["time"] = tb_grp[tb_name]  # hard link -> shared time base
            g.attrs["time_units"] = "ms"
            if c.name in query_names:  # fetched under a legacy pointname
                g.attrs["pointname"] = query_names[c.name]

        # Union new channels with whatever the file already recorded; a name that
        # is now fetched is removed from the missing list.
        fetched = _attr_names(h5, "channels_fetched") | {c.name for c in got}
        missing_names = (_attr_names(h5, "channels_missing") | {c.name for c in missing}) - fetched
        h5.attrs["channels_fetched"] = np.array(sorted(fetched), dtype="S")
        h5.attrs["channels_missing"] = np.array(sorted(missing_names), dtype="S")
    return got, missing


def _existing_channels(path, tmin, tmax, stride):
    """Names already attempted in an existing shot file IF its reduction matches.

    Returns the set of channel names already in `path` (fetched OR previously
    missing) -- but only when the file's window (tmin/tmax) and decimation equal
    this request, so we never reuse samples taken at a different resolution.
    Returns None if the file is unreadable or its reduction differs (caller then
    overwrites instead of merging).
    """
    import h5py

    want_tmin = "*" if tmin is None else float(tmin)
    want_tmax = "*" if tmax is None else float(tmax)

    def _eq(cur, want):
        if isinstance(cur, bytes):
            cur = cur.decode()
        if isinstance(want, str) or isinstance(cur, str):
            return str(cur) == str(want)
        return float(cur) == float(want)

    try:
        with h5py.File(path, "r") as h5:
            if not (
                _eq(h5.attrs.get("tmin"), want_tmin)
                and _eq(h5.attrs.get("tmax"), want_tmax)
                and int(h5.attrs.get("decimate", 1)) == int(stride)
            ):
                return None
            return _attr_names(h5, "channels_fetched") | _attr_names(h5, "channels_missing")
    except Exception:
        return None


# --- public API ---------------------------------------------------------------
def fetch_shot(
    shot: int,
    analysis: str = "both",
    *,
    backend: str = "mdsthin",
    device: str = "diiid",
    sensor_set: str | None = None,
    username: str | None = None,
    password: str | None = None,
    duo: str | None = None,
    ssh_user: str | None = None,
    ssh_password: str | None = None,
    gateway: str | None = None,
    server: str | None = None,
    tcp: bool = False,
    tmin: float | None = None,
    tmax: float | None = None,
    decimate: int = 1,
    workers: int = 4,
    batch_size: int = 40,
    per_channel: bool | None = None,
    out: str | None = None,
    compression: str = "lzf",
    force: bool = False,
    remote_host: str | None = None,
    ssh_jump: str | None = None,
    remote_dir: str = "~/magnetics_fetch",
    remote_python: str | None = None,
    progress: Progress | None = None,
) -> str:
    """Fetch one shot's magnetics signals for `analysis` and write HDF5.

    Returns the output path. `backend` defaults to "mdsthin" (laptop → DIII-D, the
    proven off-network path). Other backends: "toksearch" (run ON the cluster, where
    toksearch_d3d reads PTDATA natively), "remote" (orchestrate the toksearch pull on
    the cluster from here and copy the compact .h5 back — no manual copying), or
    "auto" (toksearch if importable, else mdsthin).
    `device` selects data/device/<device>.json, whose `network` block supplies the
    mdsip data server + SSH gateway (so the fetcher is device-agnostic); an explicit
    `gateway`/`server` still overrides. When running inside the device's site network
    we dial mdsip directly (`tcp`) and skip the gateway automatically -- see
    `network.on_site_network`; pass `tcp=True` to force the direct path off-site.
    `sensor_set` (optional) names a set under the device file's `sensor_sets`: when
    given, the pull is that set's signals (composites flattened) plus the device's
    plasma current, toroidal field, and elongation -- instead of the `analysis`
    sensor groups.
    Incremental by default: if a shot file already exists with the SAME window +
    decimation, signals already in it (fetched or previously missing) are skipped
    and the newly-pulled ones are merged in. `force=True` re-pulls everything.
    `remote_host`/`ssh_jump`/`remote_python` default (when None) to the device file's
    `network.cluster` block — the explicit cluster host, gateway ProxyJump, and env
    interpreter — so no ~/.ssh/config alias is needed; pass them to override.
    `per_channel` (None → auto) skips the mdsthin `getMany` batch attempt: it
    defaults to True off-site (where getMany reliably fails through the tunnel) and
    False on-site (where the batch round trip is the fast path).
    GUI callers pass `username` and a `progress` callback instead of relying on the
    CLI prompt/stderr bar.
    """
    if analysis not in ms.ANALYSES:
        raise ValueError(f"unknown analysis {analysis!r}; choose from {', '.join(ms.ANALYSES)}")
    progress = progress or _default_progress

    # Load the device up front: a device with its own transport (KSTAR: VPN + nkstar
    # tunnel, access="mdsplus_tree" + a `connection` block) must ALWAYS use that
    # transport, never the remote/cluster or mdsthin-gateway paths — so we decide this
    # before the backend dispatch below.
    dev = load_device(device)
    device_name = dev.get("name", device)
    _tree_transport = dev.get("access") == "mdsplus_tree" and dev.get("connection")

    if backend == "remote" and not _tree_transport:
        # Orchestrate a pull on the cluster from here; remote side runs this same
        # script with --backend toksearch and writes the file we copy back.
        from . import remote as remote_run

        kw = {} if remote_python is None else {"python": remote_python}
        return remote_run.run_remote(
            shot,
            analysis,
            host=remote_host,
            jump=ssh_jump,
            username=username,
            password=password,
            duo=duo,
            remote_dir=remote_dir,
            tmin=tmin,
            tmax=tmax,
            decimate=decimate,
            device=device,
            sensor_set=sensor_set,
            local_out_dir=(str(Path(out).parent) if out else None),
            progress=progress,
            **kw,
        )

    # Device config is the source of truth for mdsip addresses; an explicit
    # gateway/server (CLI or caller) overrides the device file. (`dev`, `device_name`,
    # and `_tree_transport` were resolved above, before the backend dispatch.)
    gateway = gateway or gateway_address(device)
    server = server or mdsip_address(device)
    # Pick the hop count for the user: inside the device's site network the data
    # host is directly reachable, so dial mdsip over TCP and skip the SSH gateway;
    # off-site (a laptop) keep the tunnel. getMany batches likewise fail through the
    # tunnel but work on-site, so per_channel tracks the same signal when unset.
    on_site = on_site_network(device)
    if not tcp and on_site:
        tcp = True
    if per_channel is None:
        per_channel = not on_site
    if backend == "mdsthin" and not _tree_transport:
        if not server:
            raise ValueError(f"device {device!r} has no 'server'; pass --server")
        if not tcp and not gateway:
            raise ValueError(
                f"device {device!r} has no 'gateway'; pass --gateway "
                "or use --tcp for a direct connection"
            )

    # Signal selection. A device sensor set (preferred) overrides the analysis
    # sensor groups: pull the set's signals plus the device's plasma params. When
    # no set is named, a device that drives selection through its own sensor sets
    # (it declares an `arrays` block -- e.g. KSTAR, which has no DIII-D PTDATA
    # analysis groups) defaults to its toroidal+poloidal arrays; otherwise fall
    # back to the per-analysis groups (DIII-D).
    stride = max(1, int(decimate))
    if sensor_set:
        set_names = [sensor_set]
    elif dev.get("arrays"):
        arr = dev["arrays"]
        set_names = _dedup([s for s in (arr.get("toroidal"), arr.get("poloidal")) if s])
    else:
        set_names = []

    if set_names:
        sensors = _dedup([s for name in set_names for s in resolve_sensor_set(dev, name)])
        # Always add the device's plasma params (current, toroidal field,
        # elongation). Each entry is {"name": ..., "tree": <optional>}: a "tree"
        # means the quantity lives in an MDSplus tree (e.g. EFIT elongation), so
        # it's fetched by (tree, node) -- not as a PTDATA pointname.
        extras: list[str] = []
        tree_signals: dict[str, list[tuple[str, str]]] = {}
        for entry in dev.get("plasma pointnames", {}).values():
            name, cands = _plasma_signal(entry)
            if cands:
                tree_signals[name] = cands
            else:
                extras.append(name)
        pointnames = _dedup(sensors + extras)
        label = "+".join(set_names)
        # Never decimate a set carrying raw bdot (dB/dt) probes -- corrupts FFTs.
        if stride > 1 and any(p.endswith("D") for p in pointnames):
            progress(0.0, "decimation disabled (set has bdot signals)")
            stride = 1
    else:
        # Per-analysis reduction policy: never decimate FFT-critical signals.
        if stride > 1 and not ms.decimate_allowed(analysis):
            progress(0.0, f"decimation disabled for {analysis}")
            stride = 1
        pointnames = ms.signals_for(analysis)
        tree_signals = ms.tree_signals_for(analysis)
        label = analysis

    # Shot-aware pointname resolution: map canonical ids -> the pointnames valid
    # at THIS shot, dropping channels the shot can't have so we never query them.
    shot_i = int(shot)
    pointnames, canonical_of, skipped = _resolve_pointnames(dev, pointnames, shot_i)
    if skipped:
        progress(0.0, f"{len(skipped)} sensors not valid at shot {shot_i}")

    if backend == "auto":
        try:
            import toksearch  # noqa: F401  # ty: ignore[unresolved-import]

            backend = "toksearch"
        except ImportError:
            backend = "mdsthin"

    # Default output lives under data/datafile/; honor an explicit --out as given.
    out_path = Path(out) if out else DATA_DIR / f"shot_{shot}.h5"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = str(out_path)

    # Incremental fetch: skip signals already in an existing shot file (with the
    # same window + decimation) and merge the rest in. `force` re-pulls all.
    merge = False
    n_skipped = 0
    if not force and out_path.exists():
        existing = _existing_channels(out_path, tmin, tmax, stride)
        if existing is None:
            sys.stderr.write(
                f"{out} exists but with a different window/decimation; "
                "overwriting (pass a separate --out to keep the old file).\n"
            )
        else:
            merge = True
            before = len(pointnames) + len(tree_signals)
            pointnames = [p for p in pointnames if p not in existing]
            tree_signals = {k: v for k, v in tree_signals.items() if k not in existing}
            n_skipped = before - (len(pointnames) + len(tree_signals))

    if merge and not pointnames and not tree_signals:
        sys.stderr.write(f"All {n_skipped} requested signals already in {out}; nothing to fetch.\n")
        return out

    t0 = time.perf_counter()
    if dev.get("access") == "mdsplus_tree" and dev.get("connection"):
        # Tree device reached via its own transport (KSTAR: KFE VPN + nkstar tunnel).
        # Ignores backend (no PTDATA); fetches each node from its per-signal tree.
        from . import kstar_transport

        try:
            from mdsthin import Connection
        except ImportError:
            sys.exit("Missing dependency: mdsthin (pure-python MDSplus thin client)")
        node_tree, default_tree = _node_tree_map(dev)
        items = []  # (canonical_id, node_to_fetch, tree, gain)
        for p in pointnames:
            canon = canonical_of.get(p, p)
            seg = segment_at(dev, canon, shot_i)
            items.append((canon, p, node_tree.get(canon, default_tree), (seg or {}).get("gain")))
        import os as _os

        _dbg = _os.environ.get("KSTAR_DEBUG") not in (None, "", "0")
        with kstar_transport.session(
            vpn_username=username,
            vpn_password=password,
            ssh_username=ssh_user,
            ssh_password=ssh_password,
            duo=duo,
            conn=dev["connection"],
            debug=_dbg,
        ) as (ssh_user_resolved, lport):

            def _connect():
                return Connection(f"{ssh_user_resolved}@127.0.0.1:{lport}")

            # The GUI/CLI window is in milliseconds (DIII-D convention), but KSTAR
            # MDS time is in SECONDS (see the t*1000 rescale in _fetch_mds_tree), so
            # the resample window must be converted to seconds -- otherwise a ms
            # window lands far past the shot and every node collapses to a single
            # sample ("degenerate result (n=1)").
            tmin_s = None if tmin is None else float(tmin) / 1000.0
            tmax_s = None if tmax is None else float(tmax) / 1000.0
            channels = _fetch_mds_tree(
                shot_i, items, connect=_connect, tmin=tmin_s, tmax=tmax_s, progress=progress
            )
    elif backend == "toksearch":
        channels = _fetch_toksearch(
            shot,
            pointnames,
            tmin=tmin,
            tmax=tmax,
            stride=stride,
            progress=progress,
            tree_signals=tree_signals,
        )
    elif backend == "mdsthin":
        # username is optional: with an ssh-config Host alias as the gateway (the
        # default), User/port/key come from ~/.ssh/config. --username overrides it.
        # GUI-supplied password → answer the SSH tunnel's auth via askpass (no
        # terminal prompt); without it ssh prompts on the tty as before.
        ssh_env, _ssh_cleanup = (None, lambda: None)
        if password and not tcp:
            from .. import sshauth

            ssh_env, _ssh_cleanup = sshauth.askpass_env(password, duo)
        try:
            channels = _fetch_mdsthin(
                shot,
                pointnames,
                username=username,
                gateway=gateway,
                server=server,
                tcp=tcp,
                tmin=tmin,
                tmax=tmax,
                stride=stride,
                workers=workers,
                batch_size=batch_size,
                progress=progress,
                tree_signals=tree_signals,
                ssh_env=ssh_env,
                per_channel=per_channel,
            )
        finally:
            _ssh_cleanup()
    else:
        raise ValueError(f"unknown backend {backend!r}")
    elapsed = time.perf_counter() - t0

    # Relabel each fetched channel from its queried (possibly legacy) pointname
    # back to the canonical sensor id, so HDF5 groups and downstream analysis stay
    # shot-agnostic by id even when an old shot was pulled under an old name; keep
    # the queried name for traceability (written as a per-channel attr).
    query_names: dict[str, str] = {}
    for c in channels:
        cid = canonical_of.get(c.name, c.name)
        if cid != c.name:
            query_names[cid] = c.name
            c.name = cid

    # out_path was resolved before the (possibly incremental) fetch above.
    n_fetch = len(pointnames) + len(tree_signals)
    got, missing = _write_h5(
        out,
        shot,
        label,
        backend,
        channels,
        compression=compression,
        tmin=tmin,
        tmax=tmax,
        stride=stride,
        device=device_name,
        source=(
            f"MDSplus tree '{dev.get('tree')}' via openTree"
            if dev.get("access") == "mdsplus_tree"
            else "PTDATA via ptdata2()"
        ),
        query_names=query_names,
        merge=merge,
    )
    skipped_note = f", {n_skipped} cached" if n_skipped else ""
    sys.stderr.write(
        f"Saved {len(got)}/{n_fetch} channels to {out} "
        f"({len(missing)} missing{skipped_note}, {backend}, {elapsed:.1f}s)\n"
    )
    if missing:
        # group missing channels by reason so a re-run is self-diagnosing
        by_reason: dict[str, list[str]] = {}
        for c in missing:
            by_reason.setdefault(c.error or "unknown", []).append(c.name)
        for reason, names in sorted(by_reason.items()):
            shown = ", ".join(names[:12]) + (" ..." if len(names) > 12 else "")
            sys.stderr.write(f"  missing [{reason}] x{len(names)}: {shown}\n")
    if skipped:
        shown = ", ".join(skipped[:12]) + (" ..." if len(skipped) > 12 else "")
        sys.stderr.write(f"  skipped [not valid at shot {shot_i}] x{len(skipped)}: {shown}\n")
    # Fail loudly on a fresh pull that resolved zero usable channels: the file is a
    # dead shot (every analysis node would 422 on it), so remove it and surface the
    # failure instead of reporting success. A merge is spared -- the existing file
    # may already hold channels from an earlier pull.
    if not got and not merge:
        Path(out).unlink(missing_ok=True)
        raise ValueError(
            f"no channels fetched for device {device_name!r} shot {shot} "
            f"({len(missing)} unavailable) -- check the sensor set / MDS tree"
        )
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch DIII-D magnetics signals (analysis-downselected) to HDF5, fast."
    )
    ap.add_argument("--shot", type=int, default=184927)
    ap.add_argument(
        "--analysis",
        choices=ms.ANALYSES,
        default="both",
        help="downselect signals by analysis type",
    )
    ap.add_argument(
        "--backend",
        choices=("mdsthin", "toksearch", "remote", "auto"),
        default="mdsthin",
        help="default mdsthin (laptop → DIII-D). 'toksearch' (cluster) "
        "and 'remote' (auto-sync + run on the cluster) are WIP. "
        "'auto' = toksearch if importable, else mdsthin",
    )
    ap.add_argument(
        "--tmin", type=float, default=None, help="window start (ms); reduces data moved"
    )
    ap.add_argument("--tmax", type=float, default=None, help="window end (ms)")
    ap.add_argument(
        "--duo", default=None, help="KSTAR 2FA: 'push' (default; sends a Duo push) or a passcode"
    )
    ap.add_argument(
        "--decimate", type=int, default=1, help="keep every Nth sample (quasi-stationary only)"
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=4,
        help="mdsthin: parallel connections (each runs whole batches)",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=40,
        help="mdsthin: channels per getMany round trip (bigger=fewer "
        "round trips; smaller=finer progress/less memory)",
    )
    ap.add_argument(
        "--per-channel",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="mdsthin: skip the getMany batch attempt and fetch one channel at a "
        "time (getMany reliably fails off-site through the tunnel). Default: auto "
        "— per-channel off-site, batch-first on-site. Use --no-per-channel to force",
    )
    ap.add_argument("--compression", choices=("none", "lzf", "gzip"), default="lzf")
    ap.add_argument(
        "--device",
        default="diiid",
        help="device config in data/device/<device>.json; supplies the "
        "mdsip gateway/server (default 'diiid')",
    )
    ap.add_argument(
        "--sensor-set",
        default=None,
        help="name of a set under the device file's 'sensor_sets'; when "
        "given, pulls that set's signals + plasma current/field/"
        "elongation instead of the --analysis groups",
    )
    ap.add_argument(
        "--gateway",
        default=None,
        help="mdsthin SSH gateway as host[:port], or an ~/.ssh/config Host alias; "
        "overrides the device file's network.jump",
    )
    ap.add_argument(
        "--server",
        default=None,
        help="mdsip host:port reached from the gateway; overrides the device file's network.mdsip",
    )
    ap.add_argument(
        "--tcp",
        action="store_true",
        help="mdsthin: force direct TCP mdsip (no SSH gateway); auto-enabled when "
        "running inside the device's site network",
    )
    ap.add_argument(
        "--username",
        default=None,
        help="GA username (mdsthin/remote); optional when the gateway "
        "ssh-config alias already sets User",
    )
    ap.add_argument("--out", default=None, help="output .h5 (default shot_<n>.h5)")
    ap.add_argument(
        "--force",
        action="store_true",
        help="re-pull every signal even if an existing shot file "
        "already has it (default: skip cached signals + merge)",
    )
    # remote backend (run the pull on the GA cluster, auto-syncing the code)
    ap.add_argument(
        "--remote-host",
        default=None,
        help="remote: cluster host; defaults to the device file's network.cluster "
        "(DIII-D: omega.gat.com). Pass to override (e.g. an ssh-config alias)",
    )
    ap.add_argument(
        "--ssh-jump",
        default=None,
        help="remote: SSH jump host[:port]; defaults to the device file's "
        "network.jump (DIII-D: cybele.gat.com:2039), and is skipped automatically "
        "when on-site. Pass an explicit value (or empty for none) to override",
    )
    ap.add_argument(
        "--remote-dir",
        default="~/magnetics_fetch",
        help="remote: dir on the cluster to sync the fetcher into",
    )
    ap.add_argument(
        "--remote-python",
        default=None,
        help="remote: cluster env interpreter to run directly (default: "
        "toksearch_env's python; no module load / conda activate)",
    )
    args = ap.parse_args(argv)

    fetch_shot(
        args.shot,
        args.analysis,
        backend=args.backend,
        device=args.device,
        sensor_set=args.sensor_set,
        username=args.username,
        duo=args.duo,
        gateway=args.gateway,
        server=args.server,
        tcp=args.tcp,
        tmin=args.tmin,
        tmax=args.tmax,
        decimate=args.decimate,
        workers=args.workers,
        batch_size=args.batch_size,
        per_channel=args.per_channel,
        out=args.out,
        force=args.force,
        compression=args.compression,
        remote_host=args.remote_host,
        ssh_jump=args.ssh_jump,
        remote_dir=args.remote_dir,
        remote_python=args.remote_python,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
