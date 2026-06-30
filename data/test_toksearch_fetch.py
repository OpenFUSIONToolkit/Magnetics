#!/usr/bin/env python3
"""
Offline tests for the HDF5 writers (no network/MDS deps).

The fetch backends need live GA/DIII-D access, but the writers are pure and
testable with synthetic Channel objects. Covers:
  * the degenerate-time-axis regression (data fetched, no usable time axis);
  * dataset-equivalence between the streaming writer (`StreamingHDF5Writer` driven
    by `stream_channels_to_h5`) and the all-at-once reference writer (`_write_h5`)
    for successful / missing / shared-timebase / distinct-nonuniform-timebase
    channels, including out-of-order batch arrival;
  * the bounded-queue backpressure that keeps peak in-flight RAM bounded.

Run:  uv run --with pytest --with h5py --with numpy \
          python -m pytest data/test_toksearch_fetch.py -q
"""
from __future__ import annotations

import random
import threading
import time

import numpy as np

from toksearch_fetch import (
    Channel,
    StreamingHDF5Writer,
    _write_h5,
    stream_channels_to_h5,
)


def _write(tmp_path, channels):
    out = str(tmp_path / "shot.h5")
    return out, _write_h5(out, 123, "both", "test", channels,
                          compression="lzf", tmin=None, tmax=None, stride=1)


def test_degenerate_time_axis_reclassified_not_crash(tmp_path):
    """A channel with data but a None/empty time axis must not crash the writer.

    This is the original bug: float(c.time[0]) on an object-dtype array holding
    None raised TypeError and killed the whole run after all fetching finished.
    """
    t = np.linspace(0.0, 10.0, 100)
    good = Channel("GOOD", t, np.ones(100, np.float32), ok=True)
    # data fetched ok=True, but dim_of came back empty -> object array of None
    bad = Channel("BAD", np.atleast_1d(np.asarray(None)),
                  np.ones(50, np.float32), ok=True)

    out, (got, missing) = _write(tmp_path, [good, bad])

    got_names = {c.name for c in got}
    missing_names = {c.name for c in missing}
    assert got_names == {"GOOD"}
    assert "BAD" in missing_names
    bad_ch = next(c for c in missing if c.name == "BAD")
    assert bad_ch.ok is False
    assert "time" in bad_ch.error

    import h5py
    with h5py.File(out, "r") as h5:
        assert "GOOD" in h5
        assert "BAD" not in h5


def test_none_and_nonfinite_time_also_dropped(tmp_path):
    none_t = Channel("NONE", None, np.ones(5, np.float32), ok=True)
    empty_t = Channel("EMPTY", np.array([]), np.array([], np.float32), ok=True)
    nan_t = Channel("NAN", np.array([0.0, np.nan, 1.0]),
                    np.ones(3, np.float32), ok=True)
    good = Channel("GOOD", np.linspace(0, 1, 3), np.ones(3, np.float32), ok=True)

    _, (got, missing) = _write(tmp_path, [none_t, empty_t, nan_t, good])

    assert {c.name for c in got} == {"GOOD"}
    assert {c.name for c in missing} == {"NONE", "EMPTY", "NAN"}


def test_identical_time_bases_deduped_and_hardlinked(tmp_path):
    """Channels sharing a time base store the vector once and hard-link to it."""
    t = np.linspace(0.0, 5.0, 64)
    chans = [Channel(f"CH{i}", t.copy(), np.full(64, i, np.float32), ok=True)
             for i in range(3)]

    out, (got, missing) = _write(tmp_path, chans)
    assert len(got) == 3 and not missing

    import h5py
    with h5py.File(out, "r") as h5:
        # exactly one stored timebase, every channel's time hard-links to it
        assert len(h5["_timebases"]) == 1
        refs = {h5[f"CH{i}"]["time"].id.__hash__() for i in range(3)}
        # all three resolve to the same underlying dataset object
        assert len(refs) == 1


def test_distinct_nonuniform_timebases_not_merged(tmp_path):
    """Two non-uniform time axes that share (shape, start, end, N) but differ in
    the interior MUST NOT be deduped. Keying the cache on metadata alone silently
    hard-links the second channel to the first and corrupts its timestamps.
    """
    tA = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0])
    tB = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 9.0, 10.0])
    # identical shape (8,), start 0.0, end 10.0, size 8 — only the interior differs
    a = Channel("A", tA.copy(), np.arange(8, dtype=np.float32), ok=True)
    b = Channel("B", tB.copy(), np.arange(8, dtype=np.float32), ok=True)

    out, (got, missing) = _write(tmp_path, [a, b])
    assert {c.name for c in got} == {"A", "B"} and not missing

    import h5py
    with h5py.File(out, "r") as h5:
        assert len(h5["_timebases"]) == 2  # two distinct vectors stored, not one
        np.testing.assert_array_equal(h5["A"]["time"][:], tA)
        np.testing.assert_array_equal(h5["B"]["time"][:], tB)


def test_all_missing_when_fetch_failed(tmp_path):
    chans = [Channel("A", ok=False, error="no data"),
             Channel("B", ok=False, error="no data")]
    out, (got, missing) = _write(tmp_path, chans)
    assert not got
    assert {c.name for c in missing} == {"A", "B"}


# --- streaming writer dataset-equivalence ------------------------------------
# The streaming writer must produce a file *dataset-equivalent* to `_write_h5`
# (same channel groups, data values+dtype, time values, timebase dedup structure,
# and root attrs) — not byte-identical, since group/dataset creation order differs
# (streaming writes channels as they arrive, possibly out of order).

def _tb_partition(h5):
    """Group channel names by the underlying timebase dataset they hard-link to,
    as a set of frozensets — the dedup structure, independent of tb naming/order.
    """
    groups: dict = {}
    for name in (k for k in h5.keys() if k != "_timebases"):
        oid = h5[name]["time"].id.__hash__()
        groups.setdefault(oid, set()).add(name)
    return {frozenset(v) for v in groups.values()}


def _assert_h5_equivalent(a_path, b_path):
    import h5py

    with h5py.File(a_path, "r") as A, h5py.File(b_path, "r") as B:
        assert set(A.attrs) == set(B.attrs)
        for k in A.attrs:
            if k in ("channels_fetched", "channels_missing"):
                # same SETS (close() sorts these by requested order separately)
                assert set(A.attrs[k]) == set(B.attrs[k]), k
            else:
                assert A.attrs[k] == B.attrs[k], k

        a_chans = sorted(k for k in A.keys() if k != "_timebases")
        b_chans = sorted(k for k in B.keys() if k != "_timebases")
        assert a_chans == b_chans
        for nm in a_chans:
            assert A[nm]["data"].dtype == B[nm]["data"].dtype, nm
            np.testing.assert_array_equal(A[nm]["data"][:], B[nm]["data"][:])
            np.testing.assert_array_equal(A[nm]["time"][:], B[nm]["time"][:])

        # identical dedup structure (shared vs distinct) and timebase count
        assert _tb_partition(A) == _tb_partition(B)
        assert len(A["_timebases"]) == len(B["_timebases"])


def _stream_write(tmp_path, channels, *, order=None, batch_size=2, shuffle=False,
                  queue_max=4, name="stream.h5"):
    """Drive the real orchestrator with a synthetic producer that emits `channels`
    as batches (optionally in shuffled batch order, to exercise out-of-order
    completion)."""
    out = str(tmp_path / name)
    if order is None:
        order = {c.name: i for i, c in enumerate(channels)}
    batches = [channels[i:i + batch_size]
               for i in range(0, len(channels), batch_size)]
    if shuffle:
        random.Random(20260630).shuffle(batches)

    def produce(sink):
        for b in batches:
            sink.put(b)

    got, missing = stream_channels_to_h5(
        out, 123, "both", "test", compression="lzf", tmin=None, tmax=None,
        stride=1, order=order, produce=produce, queue_max=queue_max)
    return out, (got, missing)


def _assert_streaming_equivalent(tmp_path, make, *, batch_size=2, shuffle=True):
    """Both writers mutate Channel objects, so each writer gets a fresh `make()`."""
    legacy = str(tmp_path / "legacy.h5")
    _write_h5(legacy, 123, "both", "test", make(),
              compression="lzf", tmin=None, tmax=None, stride=1)
    order = {c.name: i for i, c in enumerate(make())}
    stream, _ = _stream_write(tmp_path, make(), order=order,
                              batch_size=batch_size, shuffle=shuffle)
    _assert_h5_equivalent(legacy, stream)
    return stream


def _shared_tb_channels():
    t = np.linspace(0.0, 5.0, 64)
    return [Channel(f"CH{i}", t.copy(), np.full(64, i, np.float32), ok=True)
            for i in range(4)]


def _distinct_nonuniform_channels():
    # identical (shape, start, end, N); only the interior differs -> must NOT merge
    tA = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 10.0])
    tB = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 9.0, 10.0])
    return [Channel("A", tA.copy(), np.arange(8, dtype=np.float32), ok=True),
            Channel("B", tB.copy(), np.arange(8, dtype=np.float32), ok=True)]


def _mixed_channels():
    # success + missing + shared tb + reclassified-bad-time + distinct tb
    t = np.linspace(0.0, 1.0, 16)
    return [
        Channel("OK1", t.copy(), np.full(16, 1, np.float32), ok=True),
        Channel("MISS1", ok=False, error="no data"),
        Channel("OK2", t.copy(), np.full(16, 2, np.float32), ok=True),  # shares t
        Channel("BADTIME", None, np.ones(16, np.float32), ok=True),     # -> missing
        Channel("OK3", np.linspace(0.0, 2.0, 32),
                np.full(32, 3, np.float32), ok=True),                    # distinct tb
        Channel("MISS2", ok=False, error="no data"),
    ]


def test_streaming_equivalent_successful_and_shared_timebase(tmp_path):
    """Successful channels sharing a timebase: dedup -> one tb, hard-linked, and
    the streamed file matches the reference writer."""
    stream = _assert_streaming_equivalent(tmp_path, _shared_tb_channels)
    import h5py
    with h5py.File(stream, "r") as h5:
        assert len(h5["_timebases"]) == 1                 # deduped to one vector
        refs = {h5[f"CH{i}"]["time"].id.__hash__() for i in range(4)}
        assert len(refs) == 1                             # all hard-link to it


def test_streaming_equivalent_distinct_nonuniform_timebases(tmp_path):
    """Two non-uniform axes sharing (shape, start, end, N) must stay distinct
    (the 6a2fd25 content-safety invariant), and match the reference writer."""
    stream = _assert_streaming_equivalent(tmp_path, _distinct_nonuniform_channels)
    import h5py
    with h5py.File(stream, "r") as h5:
        assert len(h5["_timebases"]) == 2                 # NOT merged
        np.testing.assert_array_equal(
            h5["A"]["time"][:], _distinct_nonuniform_channels()[0].time)
        np.testing.assert_array_equal(
            h5["B"]["time"][:], _distinct_nonuniform_channels()[1].time)


def test_streaming_equivalent_with_missing_and_reclassified(tmp_path):
    """Missing (ok=False) and reclassified (no usable time) channels match the
    reference writer's fetched/missing partition."""
    stream = _assert_streaming_equivalent(tmp_path, _mixed_channels)
    import h5py
    with h5py.File(stream, "r") as h5:
        fetched = {b.decode() for b in h5.attrs["channels_fetched"]}
        missing = {b.decode() for b in h5.attrs["channels_missing"]}
        assert fetched == {"OK1", "OK2", "OK3"}
        assert missing == {"MISS1", "MISS2", "BADTIME"}
        assert "BADTIME" not in h5 and "MISS1" not in h5


def test_streaming_metadata_sorted_by_requested_order(tmp_path):
    """Batches complete out of order, but channels_fetched is sorted back into the
    requested pointname order at close."""
    chans = [Channel(f"CH{i}", np.linspace(0.0, 1.0, 8),
                     np.full(8, i, np.float32), ok=True) for i in range(6)]
    order = {f"CH{i}": i for i in range(6)}
    out, (got, missing) = _stream_write(tmp_path, chans, order=order,
                                        batch_size=2, shuffle=True)
    assert [c.name for c in got] == [f"CH{i}" for i in range(6)]
    import h5py
    with h5py.File(out, "r") as h5:
        fetched = [b.decode() for b in h5.attrs["channels_fetched"]]
    assert fetched == [f"CH{i}" for i in range(6)]


def test_bounded_queue_caps_in_flight_batches(tmp_path, monkeypatch):
    """Backpressure proof: with a slow writer, a fast producer cannot get more
    than ~queue_max batches ahead, so peak in-flight RAM is bounded by the queue
    depth, NOT by the total number of batches."""
    maxsize = 2
    n_batches = 24
    bs = 3
    total = n_batches * bs
    state = {"produced": 0, "written": 0, "max_inflight": 0}
    lock = threading.Lock()

    real_write_batch = StreamingHDF5Writer.write_batch

    def slow_write_batch(self, batch):
        time.sleep(0.003)                 # make the writer the bottleneck
        real_write_batch(self, batch)
        with lock:
            state["written"] += len(batch)

    monkeypatch.setattr(StreamingHDF5Writer, "write_batch", slow_write_batch)

    order = {f"CH{i}": i for i in range(total)}

    def produce(sink):
        for b in range(n_batches):
            batch = [Channel(f"CH{b * bs + j}", np.linspace(0.0, 1.0, 8),
                             np.full(8, b * bs + j, np.float32), ok=True)
                     for j in range(bs)]
            sink.put(batch)              # blocks once the bounded queue is full
            with lock:
                state["produced"] += len(batch)
                state["max_inflight"] = max(
                    state["max_inflight"], state["produced"] - state["written"])

    out = str(tmp_path / "shot.h5")
    got, missing = stream_channels_to_h5(
        out, 1, "both", "test", compression="lzf", tmin=None, tmax=None,
        stride=1, order=order, produce=produce, queue_max=maxsize)

    assert len(got) == total and not missing
    # In-flight = queue contents (<= maxsize batches) + the one batch the writer
    # holds; bounded regardless of `total`. An unbounded queue would let
    # max_inflight reach `total` (here 72 >> the bound 12).
    assert state["max_inflight"] <= (maxsize + 2) * bs
    assert state["produced"] == state["written"] == total
