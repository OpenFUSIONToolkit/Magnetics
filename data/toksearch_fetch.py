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
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import numpy as np

import magnetics_signals as ms

# All fetched shot files land here: data/datafile/ (next to this script).
DATA_DIR = Path(__file__).resolve().parent / "datafile"

# A progress callback: (fraction_done in [0,1], human message) -> None.
Progress = Callable[[float, str], None]


def _default_progress(frac: float, msg: str) -> None:
    """Single-line stderr progress bar (keeps the user informed during a pull)."""
    width = 28
    filled = int(width * frac)
    bar = "#" * filled + "-" * (width - filled)
    sys.stderr.write(f"\r[{bar}] {frac*100:5.1f}%  {msg:<32.32s}")
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


def _usable_time(c: "Channel") -> np.ndarray | None:
    """The channel's normalized time axis, or None if it has no usable one.

    A channel can fetch data samples yet come back with a degenerate time axis
    (dim_of/times empty or None -> an object-dtype array holding None, or a
    non-finite axis). Such a channel has no time base, so the writer reclassifies
    it as missing instead of crashing on float(c.time[0]).
    """
    if c.time is None:
        return None
    t = np.asarray(c.time)
    if (t.size == 0 or not np.issubdtype(t.dtype, np.number)
            or not np.all(np.isfinite(t))):
        return None
    return t


def _timebase_key(t: np.ndarray) -> tuple:
    """Content-address a time vector so identical vectors share storage, but two
    distinct vectors that merely share (dtype, shape, endpoints, N) never collide
    — a metadata-only key would silently hard-link them and corrupt timestamps.
    """
    return (t.dtype.str, t.shape, hashlib.sha1(np.ascontiguousarray(t)).digest())


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
    cmd = ["ssh", "-C", "-o", "ExitOnForwardFailure=yes", "-o",
           "ServerAliveInterval=30", "-N"]
    if gw_port:
        cmd += ["-p", gw_port]
    cmd += ["-L", f"{lport}:{mds_host}:{mds_port}", target]
    prompt = ("(using supplied credentials; approve Duo if pushed)" if env
              else "(your terminal will prompt for password + Duo once)")
    sys.stderr.write(
        f"Opening one SSH tunnel via {gateway} -> {mds_host}:{mds_port} "
        f"(local :{lport}).\n{prompt}\n")
    proc = subprocess.Popen(cmd, env=env)  # env may carry SSH_ASKPASS
    try:
        ready = False
        for _ in range(1200):  # up to ~120s to complete Duo + open the forward
            if proc.poll() is not None:
                raise SystemExit("SSH tunnel exited before it was ready "
                                 "(auth failed or forward refused).")
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
def _fetch_mdsthin(shot, pointnames, *, username, gateway, server, tcp,
                   tmin, tmax, stride, workers, batch_size, progress, sink,
                   ssh_env=None):
    """Pull pointnames concurrently over a pool of mdsthin connections.

    Each worker owns its own connection (mdsthin Connections are not thread-safe
    to share) and pulls a slice of the channel list. PTDATA fetches are
    server-I/O bound, so N connections give a near-linear speedup over the
    sequential one-connection loop in pull_shot_h5.py.

    Completed batches are emitted to `sink` (a bounded queue) as they finish,
    instead of being accumulated into one big list, so the single writer thread
    persists them write-as-you-go and peak RAM stays bounded to the in-flight
    batches. The bounded queue backpressures the workers: once it is full they
    block on `put`, so they cannot outrun the writer.

    Off-cluster (the default, not --tcp) all workers share ONE SSH tunnel so there
    is a single password/Duo prompt; on-network (--tcp) each worker connects to
    mdsip directly. Reduction (window + stride) is pushed server-side via a TDI
    subscript so only the reduced samples cross the wire.
    """
    try:
        from mdsthin import Connection
    except ImportError:
        sys.exit("Missing dependency: pip/uv install mdsthin  "
                 "(pure-python MDSplus thin client)")

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
    data_expr = f"(ptdata2($, $)){suffix}"          # $1=pointname, $2=shot
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
    batches = [pointnames[i:i + batch_size]
               for i in range(0, n, batch_size)]
    workers = max(1, min(workers, len(batches)))

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
                        out.append(Channel(
                            pt, t, y.astype(np.float32, copy=False), ok=True))
                    except Exception as exc:  # per-channel error in the batch
                        out.append(Channel(pt, ok=False, error=str(exc)))
                tick(batch[-1], k=len(batch))
                return out, True
            except Exception as exc:  # whole-batch failure -> fall back
                sys.stderr.write(
                    f"\ngetMany unavailable ({exc}); using per-channel fetch.\n")
                use_many = False
        # per-channel fallback
        for pt in batch:
            try:
                t, y, ok = fetch_one(conn, pt)
                if ok:
                    out.append(Channel(pt, t, y.astype(np.float32, copy=False),
                                       ok=True))
                else:
                    out.append(Channel(pt, ok=False, error="no data"))
            except Exception as exc:
                out.append(Channel(pt, ok=False, error=str(exc)))
            tick(pt)
        return out, False

    def run_worker(connect, my_batches):
        conn = connect()
        use_many = True
        for batch in my_batches:
            got, use_many = fetch_batch(conn, batch, use_many)
            sink.put(got)  # emit a completed batch (bounded queue -> backpressure)

    def run_all(connect, label):
        progress(0.0, label)
        # round-robin batches to workers
        assigned: list[list[list[str]]] = [[] for _ in range(workers)]
        for i, b in enumerate(batches):
            assigned[i % workers].append(b)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(run_worker, connect, a)
                       for a in assigned if a]
            for fut in as_completed(futures):
                fut.result()  # surface worker exceptions loudly (writer ordering)

    if tcp:
        # On-network: each worker dials mdsip directly (no gateway, no auth race).
        run_all(lambda: Connection(f"{username}@{mds_host}:{mds_port}"),
                f"{len(batches)} batches x{batch_size} ({workers} conns)")
        return
    # Off-network: one SSH tunnel, then a few TCP mdsip conns through it.
    with _ssh_tunnel(username, gateway, mds_host, mds_port, env=ssh_env) as lport:
        run_all(lambda: Connection(f"{username}@127.0.0.1:{lport}"),
                f"{len(batches)} batches x{batch_size} via tunnel")


# --- toksearch backend (cluster, native local PTDATA) -------------------------
def _fetch_toksearch(shot, pointnames, *, tmin, tmax, stride, progress, sink):
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

    Each extracted channel is emitted to `sink` (the bounded queue) as a one-item
    batch so the single writer thread persists it write-as-you-go.
    """
    try:
        from toksearch import Pipeline
    except ImportError:
        sys.exit("Missing dependency: toksearch is not installed in this "
                 "environment. Run on the GA cluster's toksearch env, or use "
                 "--backend mdsthin.")
    try:
        from toksearch_d3d import PtDataSignal
    except ImportError:
        try:  # older/newer layouts re-export it from core toksearch
            from toksearch import PtDataSignal  # type: ignore
        except ImportError:
            sys.exit("Missing dependency: toksearch_d3d (the DIII-D PTDATA plugin) "
                     "is not installed. Install toksearch_d3d, or use "
                     "--backend mdsthin.")

    pipe = Pipeline([shot])
    for pt in pointnames:
        pipe.fetch(pt, PtDataSignal(pt))  # ical=1 default == ptdata2()

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
    for i, pt in enumerate(pointnames, 1):
        sig = None if pt in errors else rec[pt]
        # a toksearch signal is a dict {n_over, n_under, data, times, units}; a
        # missing pointname is None (and/or recorded in errors above).
        if sig is None or "data" not in sig:
            err = "no data"
            if pt in errors:
                err = str(errors[pt].get("type", "no data")) if hasattr(
                    errors[pt], "get") else "no data"
            ch = Channel(pt, ok=False, error=err)
        else:
            y = np.atleast_1d(np.asarray(sig["data"]))
            t = np.atleast_1d(np.asarray(sig["times"]))
            if y.size <= 1:  # degenerate -> treat as no data
                ch = Channel(pt, ok=False, error="no data")
            else:
                t, y = _reduce(t, y, tmin, tmax, stride)
                ch = Channel(pt, t.astype(np.float64, copy=False),
                             y.astype(np.float32, copy=False), ok=True)
        sink.put([ch])  # emit one completed channel (bounded queue -> backpressure)
        progress(i / n, pt)


# --- HDF5 writer (lzf + chunked + deduped time bases) -------------------------
# `_write_h5` is the all-at-once reference writer: it materializes the whole
# channel list before writing. `StreamingHDF5Writer` below produces a
# dataset-equivalent file while consuming channels incrementally so peak RAM is
# bounded by the in-flight batches, not the whole shot. Both share the same
# reclassify (`_usable_time`) and content-address (`_timebase_key`) logic.
def _write_h5(path, shot, analysis, backend, channels, *, compression,
              tmin, tmax, stride):
    import h5py

    comp = None if compression in (None, "none") else compression
    missing = [c for c in channels if not c.ok]

    # Reclassify channels whose time axis is unusable as missing (see _usable_time).
    got = []
    for c in (ch for ch in channels if ch.ok):
        t = _usable_time(c)
        if t is None:
            c.ok = False
            c.error = "no usable time axis"
            missing.append(c)
        else:
            c.time = t
            got.append(c)

    with h5py.File(path, "w") as h5:
        h5.attrs["shot"] = shot
        h5.attrs["device"] = "DIII-D"
        h5.attrs["source"] = "PTDATA via ptdata2()"
        h5.attrs["analysis"] = analysis
        h5.attrs["backend"] = backend
        h5.attrs["tmin"] = "*" if tmin is None else float(tmin)
        h5.attrs["tmax"] = "*" if tmax is None else float(tmax)
        h5.attrs["decimate"] = int(stride)

        # Dedup identical time bases: store each unique vector once and hard-link
        # every channel's "time" to it. inspect_h5.py still sees a per-channel
        # "time" dataset (a hard link is transparent), but we write it once.
        tb_grp = h5.create_group("_timebases")
        tb_cache: dict[tuple, str] = {}
        tb_n = 0
        for c in got:
            key = _timebase_key(c.time)
            tb_name = tb_cache.get(key)
            if tb_name is None:
                tb_name = f"tb{tb_n}"
                tb_n += 1
                tb_grp.create_dataset(
                    tb_name, data=c.time, compression=comp,
                    chunks=True if comp else None)
                tb_grp[tb_name].attrs["time_units"] = "ms"
                tb_cache[key] = tb_name

            g = h5.create_group(c.name)
            g.create_dataset("data", data=c.data, compression=comp,
                             chunks=True if comp else None)
            g["time"] = tb_grp[tb_name]  # hard link -> shared time base
            g.attrs["time_units"] = "ms"

        h5.attrs["channels_fetched"] = np.array([c.name for c in got], dtype="S")
        h5.attrs["channels_missing"] = np.array([c.name for c in missing],
                                                dtype="S")
    return got, missing


# --- bounded streaming HDF5 writer --------------------------------------------
class StreamingHDF5Writer:
    """Write-as-you-go HDF5 writer that bounds peak RAM to the in-flight batches.

    Consumes completed `Channel`s incrementally (one batch at a time), carries the
    timebase content-address map across batches (only the hash->name dict lives on,
    never the vectors), and writes each channel's `data` + a hard-linked `time` as
    it arrives. Output is *dataset-equivalent* to `_write_h5` (same groups, data,
    timebase dedup structure, and root attrs) though group creation order differs.

    A single thread owns the one h5py handle (h5py is single-writer): the writer is
    never touched from more than one thread. Writes go to a temp file in the
    destination dir and are published with `os.replace` only on a clean `close()`,
    so a failed fetch never exposes a partial `.h5` (see `abort`).
    """

    def __init__(self, path, shot, analysis, backend, *, compression,
                 tmin, tmax, stride, order):
        import h5py

        self._final_path = Path(path)
        # Hidden, pid-tagged temp sibling on the same filesystem -> atomic replace.
        self._tmp_path = self._final_path.with_name(
            f".{self._final_path.name}.{os.getpid()}.tmp")
        self._comp = None if compression in (None, "none") else compression
        self._order = order  # {pointname: index} -> deterministic close ordering
        self._got: list[Channel] = []
        self._missing: list[Channel] = []
        self._tb_cache: dict[tuple, str] = {}  # carried across batches
        self._tb_n = 0

        self._h5 = h5py.File(self._tmp_path, "w")
        self._h5.attrs["shot"] = shot
        self._h5.attrs["device"] = "DIII-D"
        self._h5.attrs["source"] = "PTDATA via ptdata2()"
        self._h5.attrs["analysis"] = analysis
        self._h5.attrs["backend"] = backend
        self._h5.attrs["tmin"] = "*" if tmin is None else float(tmin)
        self._h5.attrs["tmax"] = "*" if tmax is None else float(tmax)
        self._h5.attrs["decimate"] = int(stride)
        self._tb_grp = self._h5.create_group("_timebases")

    def write_channel(self, c: Channel) -> None:
        """Persist one completed channel (or record it missing)."""
        if not c.ok:
            self._missing.append(c)
            return
        t = _usable_time(c)
        if t is None:
            c.ok = False
            c.error = "no usable time axis"
            self._missing.append(c)
            return
        c.time = t

        key = _timebase_key(t)
        tb_name = self._tb_cache.get(key)
        if tb_name is None:
            tb_name = f"tb{self._tb_n}"
            self._tb_n += 1
            self._tb_grp.create_dataset(
                tb_name, data=t, compression=self._comp,
                chunks=True if self._comp else None)
            self._tb_grp[tb_name].attrs["time_units"] = "ms"
            self._tb_cache[key] = tb_name

        g = self._h5.create_group(c.name)
        g.create_dataset("data", data=c.data, compression=self._comp,
                         chunks=True if self._comp else None)
        g["time"] = self._tb_grp[tb_name]  # hard link -> shared time base
        g.attrs["time_units"] = "ms"
        self._got.append(c)

    def write_batch(self, channels) -> None:
        """Persist a completed batch of channels (the queue unit of work)."""
        for c in channels:
            self.write_channel(c)

    def close(self) -> tuple[list[Channel], list[Channel]]:
        """Finalize metadata, close the file, and atomically publish it.

        Channels complete out of order, so `channels_fetched`/`channels_missing`
        are sorted back into the requested pointname order here.
        """
        self._got.sort(key=lambda c: self._order[c.name])
        self._missing.sort(key=lambda c: self._order[c.name])
        self._h5.attrs["channels_fetched"] = np.array(
            [c.name for c in self._got], dtype="S")
        self._h5.attrs["channels_missing"] = np.array(
            [c.name for c in self._missing], dtype="S")
        self._h5.close()
        os.replace(self._tmp_path, self._final_path)
        return self._got, self._missing

    def abort(self) -> None:
        """Drop the partial temp file without publishing it (failure path)."""
        self._h5.close()  # h5py: closing an already-closed file is a no-op
        if self._tmp_path.exists():
            self._tmp_path.unlink()


_DONE = object()  # queue sentinel: no more batches will be emitted


class _WriterThread(threading.Thread):
    """The single HDF5 consumer: drains the bounded queue into the writer.

    On a write error it records the exception and keeps draining (without writing)
    so backpressured producers blocked on a full queue cannot deadlock; the
    orchestrator re-raises the captured error after `join()`.
    """

    def __init__(self, sink: "queue.Queue", writer: StreamingHDF5Writer):
        super().__init__(name="hdf5-writer")
        self._sink = sink
        self._writer = writer
        self.error: Exception | None = None

    def run(self) -> None:
        while True:
            batch = self._sink.get()
            if batch is _DONE:
                return
            if self.error is None:
                try:
                    self._writer.write_batch(batch)
                except Exception as exc:  # surfaced on the main thread after join
                    self.error = exc


def stream_channels_to_h5(path, shot, analysis, backend, *, compression,
                          tmin, tmax, stride, order, produce, queue_max):
    """Stream the fetch backend's channels into one HDF5 file, RAM-bounded.

    `produce(sink)` runs the backend (mdsthin/toksearch) and emits completed
    `Channel` batches (lists) to `sink`, a `queue.Queue(maxsize=queue_max)`. One
    `_WriterThread` drains the queue into a `StreamingHDF5Writer`. The queue bound
    is backpressure: producers block once it is full, so peak in-flight RAM is
    ~queue_max + one batch, never the whole shot. Returns (got, missing).
    """
    sink: queue.Queue = queue.Queue(maxsize=queue_max)
    writer = StreamingHDF5Writer(path, shot, analysis, backend,
                                 compression=compression, tmin=tmin, tmax=tmax,
                                 stride=stride, order=order)
    consumer = _WriterThread(sink, writer)
    consumer.start()
    published = False
    try:
        produce(sink)
        sink.put(_DONE)
        consumer.join()
        if consumer.error is not None:
            raise consumer.error
        result = writer.close()  # publishes via os.replace
        published = True
        return result
    finally:
        if not published:
            # Producer/consumer error (or Ctrl-C): stop the writer thread and drop
            # the partial temp file. The in-flight exception propagates unchanged.
            sink.put(_DONE)
            consumer.join()
            writer.abort()


# --- public API ---------------------------------------------------------------
def fetch_shot(shot: int, analysis: str = "both", *, backend: str = "mdsthin",
               username: str | None = None, password: str | None = None,
               duo: str | None = None, gateway: str = "cybele.gat.com:2039",
               server: str = "atlas.gat.com:8000", tcp: bool = False,
               tmin: float | None = None, tmax: float | None = None,
               decimate: int = 1, workers: int = 4, batch_size: int = 40,
               out: str | None = None, compression: str = "lzf",
               remote_host: str = "omega", ssh_jump: str = "cybele.gat.com:2039",
               remote_dir: str = "~/magnetics_fetch", remote_setup: str | None = None,
               progress: Progress | None = None) -> str:
    """Fetch one shot's magnetics signals for `analysis` and write HDF5.

    Returns the output path. `backend` defaults to "mdsthin" (laptop → DIII-D, the
    proven path). Other backends: "toksearch" (cluster, **work in progress**),
    "remote" (auto-sync the fetcher to the GA cluster, run the toksearch pull
    there, copy the .h5 back — no manual copying; also WIP since it relies on
    toksearch), or "auto" (toksearch if importable, else mdsthin).
    GUI callers pass `username` and a `progress` callback instead of relying on the
    CLI prompt/stderr bar.
    """
    if analysis not in ms.ANALYSES:
        raise ValueError(f"unknown analysis {analysis!r}; "
                         f"choose from {', '.join(ms.ANALYSES)}")
    progress = progress or _default_progress

    if backend == "remote":
        # Orchestrate a pull on the cluster from here; remote side runs this same
        # script with --backend toksearch and writes the file we copy back.
        import remote_run
        kw = {} if remote_setup is None else {"setup": remote_setup}
        return remote_run.run_remote(
            shot, analysis, host=remote_host, jump=ssh_jump, username=username,
            password=password, duo=duo, remote_dir=remote_dir, tmin=tmin,
            tmax=tmax, decimate=decimate,
            local_out_dir=(str(Path(out).parent) if out else None),
            progress=progress, **kw)

    # Per-analysis reduction policy: never decimate FFT-critical signals.
    stride = max(1, int(decimate))
    if stride > 1 and not ms.decimate_allowed(analysis):
        progress(0.0, f"decimation disabled for {analysis}")
        stride = 1

    pointnames = ms.signals_for(analysis)

    if backend == "auto":
        try:
            import toksearch  # noqa: F401
            backend = "toksearch"
        except ImportError:
            backend = "mdsthin"

    # Default output lives under data/datafile/; honor an explicit --out as given.
    out_path = Path(out) if out else DATA_DIR / f"shot_{shot}.h5"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = str(out_path)
    order = {pt: i for i, pt in enumerate(pointnames)}  # deterministic close order
    queue_max = max(2, workers)  # in-flight bound: ~queue_max + one batch per side

    # Build the backend producer: it emits completed Channel batches to the queue
    # the streaming writer drains. h5py is single-writer, so one writer thread owns
    # the file while these workers fetch.
    ssh_env, _ssh_cleanup = (None, lambda: None)
    if backend == "toksearch":
        def produce(sink):
            _fetch_toksearch(shot, pointnames, tmin=tmin, tmax=tmax,
                             stride=stride, progress=progress, sink=sink)
    elif backend == "mdsthin":
        # username is optional: with an ssh-config Host alias as the gateway (the
        # default), User/port/key come from ~/.ssh/config. --username overrides it.
        # GUI-supplied password → answer the SSH tunnel's auth via askpass (no
        # terminal prompt); without it ssh prompts on the tty as before.
        if password and not tcp:
            import sshauth
            ssh_env, _ssh_cleanup = sshauth.askpass_env(password, duo)

        def produce(sink):
            _fetch_mdsthin(
                shot, pointnames, username=username, gateway=gateway,
                server=server, tcp=tcp, tmin=tmin, tmax=tmax, stride=stride,
                workers=workers, batch_size=batch_size, progress=progress,
                sink=sink, ssh_env=ssh_env)
    else:
        raise ValueError(f"unknown backend {backend!r}")

    t0 = time.perf_counter()
    try:
        got, missing = stream_channels_to_h5(
            out, shot, analysis, backend, compression=compression, tmin=tmin,
            tmax=tmax, stride=stride, order=order, produce=produce,
            queue_max=queue_max)
    finally:
        _ssh_cleanup()
    elapsed = time.perf_counter() - t0
    sys.stderr.write(
        f"Saved {len(got)}/{len(pointnames)} channels to {out} "
        f"({len(missing)} missing, {backend}, {elapsed:.1f}s)\n")
    if missing:
        # group missing channels by reason so a re-run is self-diagnosing
        by_reason: dict[str, list[str]] = {}
        for c in missing:
            by_reason.setdefault(c.error or "unknown", []).append(c.name)
        for reason, names in sorted(by_reason.items()):
            shown = ", ".join(names[:12]) + (" ..." if len(names) > 12 else "")
            sys.stderr.write(f"  missing [{reason}] x{len(names)}: {shown}\n")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch DIII-D magnetics signals (analysis-downselected) "
                    "to HDF5, fast.")
    ap.add_argument("--shot", type=int, default=184927)
    ap.add_argument("--analysis", choices=ms.ANALYSES, default="both",
                    help="downselect signals by analysis type")
    ap.add_argument("--backend",
                    choices=("mdsthin", "toksearch", "remote", "auto"),
                    default="mdsthin",
                    help="default mdsthin (laptop → DIII-D). 'toksearch' (cluster) "
                         "and 'remote' (auto-sync + run on the cluster) are WIP. "
                         "'auto' = toksearch if importable, else mdsthin")
    ap.add_argument("--tmin", type=float, default=None,
                    help="window start (ms); reduces data moved")
    ap.add_argument("--tmax", type=float, default=None, help="window end (ms)")
    ap.add_argument("--decimate", type=int, default=1,
                    help="keep every Nth sample (quasi-stationary only)")
    ap.add_argument("--workers", type=int, default=4,
                    help="mdsthin: parallel connections (each runs whole batches)")
    ap.add_argument("--batch-size", type=int, default=40,
                    help="mdsthin: channels per getMany round trip (bigger=fewer "
                         "round trips; smaller=finer progress/less memory)")
    ap.add_argument("--compression", choices=("none", "lzf", "gzip"),
                    default="lzf")
    ap.add_argument("--gateway", default="cybele.gat.com:2039",
                    help="mdsthin SSH gateway as host[:port] (default "
                         "cybele.gat.com:2039) — or an ~/.ssh/config Host alias")
    ap.add_argument("--server", default="atlas.gat.com:8000",
                    help="mdsip host:port reached from the gateway")
    ap.add_argument("--tcp", action="store_true",
                    help="mdsthin: direct TCP mdsip instead of SSH gateway")
    ap.add_argument("--username", default=None,
                    help="GA username (mdsthin/remote); optional when the gateway "
                         "ssh-config alias already sets User")
    ap.add_argument("--out", default=None, help="output .h5 (default shot_<n>.h5)")
    # remote backend (run the pull on the GA cluster, auto-syncing the code)
    ap.add_argument("--remote-host", default="omega",
                    help="remote: cluster host to run toksearch on")
    ap.add_argument("--ssh-jump", default="cybele.gat.com:2039",
                    help="remote: SSH jump/gateway host[:port] (empty to disable)")
    ap.add_argument("--remote-dir", default="~/magnetics_fetch",
                    help="remote: dir on the cluster to sync the fetcher into")
    ap.add_argument("--remote-setup", default=None,
                    help="remote: shell to load toksearch (default: module purge "
                         "&& module load conda && conda activate toksearch_env)")
    args = ap.parse_args(argv)

    fetch_shot(args.shot, args.analysis, backend=args.backend,
               username=args.username, gateway=args.gateway, server=args.server,
               tcp=args.tcp, tmin=args.tmin, tmax=args.tmax,
               decimate=args.decimate, workers=args.workers,
               batch_size=args.batch_size, out=args.out,
               compression=args.compression, remote_host=args.remote_host,
               ssh_jump=args.ssh_jump, remote_dir=args.remote_dir,
               remote_setup=args.remote_setup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
