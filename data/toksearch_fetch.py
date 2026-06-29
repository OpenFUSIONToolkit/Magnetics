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
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

import numpy as np

import magnetics_signals as ms

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


# --- mdsthin backend (laptop / remote, parallel across channels) --------------
def _fetch_mdsthin(shot, pointnames, *, username, gateway, server, tcp,
                   tmin, tmax, stride, workers, progress):
    """Pull pointnames concurrently over a pool of mdsthin connections.

    Each worker owns its own connection (mdsthin Connections are not thread-safe
    to share) and pulls a slice of the channel list. PTDATA fetches are
    server-I/O bound, so N connections give a near-linear speedup over the
    sequential one-connection loop in pull_shot_h5.py.

    Reduction (window + stride) is pushed server-side via a TDI subscript so only
    the reduced samples cross the wire.
    """
    try:
        from mdsthin import Connection
    except ImportError:
        sys.exit("Missing dependency: pip/uv install mdsthin  "
                 "(pure-python MDSplus thin client)")

    mds = server.split("://", 1)[-1].split("@", 1)[-1]
    mds_host, _, mds_port = mds.partition(":")
    mds_port = int(mds_port or 8000)

    def connect():
        if tcp:
            return Connection(f"{username}@{mds_host}:{mds_port}")
        return Connection(f"sshp://{username}@{gateway}:{mds_port}",
                          sshp_host=mds_host)

    # Build a server-side reducing expression so PTDATA returns only what we keep.
    # ptdata2 gives a *signal*; all reduction happens on `_s` (a signal slices by
    # its own dimension's units for a value window, by index for a strided range),
    # then we read its dimension back with dim_of -- so the time axis always
    # matches the reduced data. (Slicing dim_of() directly would be index-based
    # and mismatch the value window.)
    def fetch_one(conn, pt):
        conn.get(f'_s = ptdata2("{pt}", {shot})')
        if tmin is not None or tmax is not None:
            lo = "*" if tmin is None else repr(float(tmin))
            hi = "*" if tmax is None else repr(float(tmax))
            # window in engineering units (ms) via the signal's own time axis
            conn.get(f"_s = _s[{lo} : {hi}]")
        if stride > 1:
            conn.get(f"_s = _s[0 : * : {stride}]")  # decimate by index
        data = np.atleast_1d(conn.get("_s").data())
        # ptdata2 returns a length-1 [0] when a pointname has no data
        if data.size <= 1 and (data.size == 0 or data[0] == 0):
            return None, None, False
        t = np.atleast_1d(conn.get("dim_of(_s)").data())
        return t, data, True

    n = len(pointnames)
    done = 0
    results: list[Channel] = []

    # Partition channels across `workers` connections.
    workers = max(1, min(workers, n))
    chunks: list[list[str]] = [[] for _ in range(workers)]
    for i, pt in enumerate(pointnames):
        chunks[i % workers].append(pt)

    def run_chunk(chunk):
        conn = connect()
        out = []
        for pt in chunk:
            try:
                t, y, ok = fetch_one(conn, pt)
                if ok:
                    out.append(Channel(pt, t, y.astype(np.float32, copy=False),
                                       ok=True))
                else:
                    out.append(Channel(pt, ok=False, error="no data"))
            except Exception as exc:  # broad: record and keep going
                out.append(Channel(pt, ok=False, error=str(exc)))
        return out

    progress(0.0, f"connecting ({workers} conns)")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(run_chunk, c) for c in chunks if c]
        for fut in as_completed(futures):
            for ch in fut.result():
                results.append(ch)
                done += 1
                progress(done / n, ch.name)
    # restore catalog order for deterministic output
    order = {pt: i for i, pt in enumerate(pointnames)}
    results.sort(key=lambda c: order[c.name])
    return results


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
    got = [c for c in channels if c.ok]
    missing = [c for c in channels if not c.ok]

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
               decimate: int = 1, workers: int = 8,
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
            progress=progress)
    else:
        raise ValueError(f"unknown backend {backend!r}")
    elapsed = time.perf_counter() - t0

    out = out or f"shot_{shot}.h5"
    got, missing = _write_h5(out, shot, analysis, backend, channels,
                             compression=compression, tmin=tmin, tmax=tmax,
                             stride=stride)
    sys.stderr.write(
        f"Saved {len(got)}/{len(pointnames)} channels to {out} "
        f"({len(missing)} missing, {backend}, {elapsed:.1f}s)\n")
    if missing:
        sys.stderr.write("Missing: " + ", ".join(c.name for c in missing) + "\n")
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
    ap.add_argument("--workers", type=int, default=8,
                    help="mdsthin: parallel connections")
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
               decimate=args.decimate, workers=args.workers, out=args.out,
               compression=args.compression)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
