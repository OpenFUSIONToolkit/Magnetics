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
import socket
import subprocess
import sys
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


@contextlib.contextmanager
def _ssh_tunnel(username, gateway, mds_host, mds_port):
    """Open ONE authenticated SSH local-forward to the mdsip server.

    Off-cluster, parallel mdsip needs parallelism WITHOUT N separate logins: with
    2FA/Duo you can only authenticate once. So we forward a local port through the
    gateway to the mdsip host a single time (one interactive password + Duo
    prompt), and every worker then opens a plain-TCP mdsip connection to
    127.0.0.1:<lport>, multiplexed over the one ssh connection.

    Yields the local port. The ssh subprocess inherits the terminal so its
    password/Duo prompt works; it is torn down on exit.
    """
    # grab a free local port
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    lport = s.getsockname()[1]
    s.close()

    cmd = ["ssh", "-o", "ExitOnForwardFailure=yes", "-o",
           "ServerAliveInterval=30", "-N",
           "-L", f"{lport}:{mds_host}:{mds_port}", f"{username}@{gateway}"]
    sys.stderr.write(
        f"Opening one SSH tunnel via {gateway} -> {mds_host}:{mds_port} "
        f"(local :{lport}).\n(your terminal will prompt for password + Duo "
        f"once)\n")
    proc = subprocess.Popen(cmd)  # inherit stdio -> interactive auth on the tty
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
                   tmin, tmax, stride, workers, batch_size, progress):
    """Pull pointnames concurrently over a pool of mdsthin connections.

    Each worker owns its own connection (mdsthin Connections are not thread-safe
    to share) and pulls a slice of the channel list. PTDATA fetches are
    server-I/O bound, so N connections give a near-linear speedup over the
    sequential one-connection loop in pull_shot_h5.py.

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
            futures = [ex.submit(run_worker, connect, a)
                       for a in assigned if a]
            for fut in as_completed(futures):
                results.extend(fut.result())
        order = {pt: i for i, pt in enumerate(pointnames)}  # deterministic output
        results.sort(key=lambda c: order[c.name])
        return results

    if tcp:
        # On-network: each worker dials mdsip directly (no gateway, no auth race).
        return run_all(lambda: Connection(f"{username}@{mds_host}:{mds_port}"),
                       f"{len(batches)} batches x{batch_size} ({workers} conns)")
    # Off-network: one SSH tunnel, then a few TCP mdsip conns through it.
    with _ssh_tunnel(username, gateway, mds_host, mds_port) as lport:
        return run_all(lambda: Connection(f"{username}@127.0.0.1:{lport}"),
                       f"{len(batches)} batches x{batch_size} via tunnel")


# --- toksearch backend (cluster, parallel across shots) -----------------------
def _fetch_toksearch(shot, pointnames, *, tmin, tmax, stride, progress):
    """Pull pointnames for a shot via a toksearch Pipeline.

    A single shot is one record; the same pipeline parallelizes across shots when
    given a list (batch-ready). We reduce client-side after the fetch -- toksearch
    PtDataSignal window/resample options vary by version, so windowing the
    returned arrays keeps this backend-version agnostic.
    """
    try:
        from toksearch import Pipeline, PtDataSignal
    except ImportError:
        sys.exit("Missing dependency: toksearch is not installed in this "
                 "environment. Run on the GA cluster's toksearch env, or use "
                 "--backend mdsthin.")

    pipe = Pipeline([shot])
    for pt in pointnames:
        pipe.fetch(pt, PtDataSignal(pt))

    progress(0.0, "running toksearch pipeline")
    # Prefer the parallel backends; fall back gracefully to serial.
    records = None
    for runner in ("compute_ray", "compute_multiprocessing", "compute_serial"):
        fn = getattr(pipe, runner, None)
        if fn is None:
            continue
        try:
            records = fn()
            break
        except Exception:  # backend unavailable (no ray cluster, etc.)
            continue
    if records is None:
        sys.exit("toksearch could not run any compute backend.")

    rec = records[0]
    n = len(pointnames)
    results: list[Channel] = []
    for i, pt in enumerate(pointnames, 1):
        sig = rec.get(pt) if hasattr(rec, "get") else rec[pt]
        if sig is None:
            results.append(Channel(pt, ok=False, error="no data"))
        else:
            # toksearch returns a dict-like {'data':..., 'times':...}
            y = np.atleast_1d(np.asarray(sig["data"]))
            t = np.atleast_1d(np.asarray(sig.get("times", sig.get("time"))))
            t, y = _reduce(t, y, tmin, tmax, stride)
            results.append(Channel(pt, t.astype(np.float64, copy=False),
                                   y.astype(np.float32, copy=False), ok=True))
        progress(i / n, pt)
    return results


# --- HDF5 writer (lzf + chunked + deduped time bases) -------------------------
def _write_h5(path, shot, analysis, backend, channels, *, compression,
              tmin, tmax, stride):
    import h5py

    comp = None if compression in (None, "none") else compression
    missing = [c for c in channels if not c.ok]

    # A channel can fetch data samples yet come back with a degenerate time axis
    # (dim_of/times empty or None -> an object-dtype array holding None). Such a
    # channel has no usable time base, so reclassify it as missing instead of
    # crashing the writer on float(c.time[0]).
    got = []
    for c in (ch for ch in channels if ch.ok):
        t = None if c.time is None else np.asarray(c.time)
        if (t is None or t.size == 0
                or not np.issubdtype(t.dtype, np.number)
                or not np.all(np.isfinite(t))):
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
            key = (c.time.shape, float(c.time[0]), float(c.time[-1]),
                   c.time.size)
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


# --- public API ---------------------------------------------------------------
def fetch_shot(shot: int, analysis: str = "both", *, backend: str = "auto",
               username: str | None = None, gateway: str = "cybele.gat.com",
               server: str = "atlas.gat.com:8000", tcp: bool = False,
               tmin: float | None = None, tmax: float | None = None,
               decimate: int = 1, workers: int = 4, batch_size: int = 40,
               out: str | None = None, compression: str = "lzf",
               progress: Progress | None = None) -> str:
    """Fetch one shot's magnetics signals for `analysis` and write HDF5.

    Returns the output path. `backend` is "auto" (toksearch if importable, else
    mdsthin), "toksearch", or "mdsthin". GUI callers pass `username` and a
    `progress` callback instead of relying on the CLI prompt/stderr bar.
    """
    if analysis not in ms.ANALYSES:
        raise ValueError(f"unknown analysis {analysis!r}; "
                         f"choose from {', '.join(ms.ANALYSES)}")
    progress = progress or _default_progress

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

    t0 = time.perf_counter()
    if backend == "toksearch":
        channels = _fetch_toksearch(shot, pointnames, tmin=tmin, tmax=tmax,
                                    stride=stride, progress=progress)
    elif backend == "mdsthin":
        if not username:
            username = input("GA username: ").strip()
        if not username:
            sys.exit("A username is required for the mdsthin backend.")
        channels = _fetch_mdsthin(
            shot, pointnames, username=username, gateway=gateway, server=server,
            tcp=tcp, tmin=tmin, tmax=tmax, stride=stride, workers=workers,
            batch_size=batch_size, progress=progress)
    else:
        raise ValueError(f"unknown backend {backend!r}")
    elapsed = time.perf_counter() - t0

    # Default output lives under data/datafile/; honor an explicit --out as given.
    out_path = Path(out) if out else DATA_DIR / f"shot_{shot}.h5"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = str(out_path)
    got, missing = _write_h5(out, shot, analysis, backend, channels,
                             compression=compression, tmin=tmin, tmax=tmax,
                             stride=stride)
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
    ap.add_argument("--backend", choices=("auto", "toksearch", "mdsthin"),
                    default="auto")
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
    ap.add_argument("--gateway", default="cybele.gat.com",
                    help="mdsthin SSH gateway host")
    ap.add_argument("--server", default="atlas.gat.com:8000",
                    help="mdsip host:port reached from the gateway")
    ap.add_argument("--tcp", action="store_true",
                    help="mdsthin: direct TCP mdsip instead of SSH gateway")
    ap.add_argument("--username", default=None,
                    help="GA username (mdsthin); prompted if omitted")
    ap.add_argument("--out", default=None, help="output .h5 (default shot_<n>.h5)")
    args = ap.parse_args(argv)

    fetch_shot(args.shot, args.analysis, backend=args.backend,
               username=args.username, gateway=args.gateway, server=args.server,
               tcp=args.tcp, tmin=args.tmin, tmax=args.tmax,
               decimate=args.decimate, workers=args.workers,
               batch_size=args.batch_size, out=args.out,
               compression=args.compression)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
