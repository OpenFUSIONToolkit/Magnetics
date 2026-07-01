#!/usr/bin/env python3
"""
Offline tests for the HDF5 writer (no network/MDS deps).

The fetch backends need live GA/DIII-D access, but `_write_h5` is pure and
testable with synthetic Channel objects. Covers the regression where a channel
fetches data samples but comes back with a degenerate time axis.

Run:  uv run python -m pytest tests/test_toksearch_writer.py -q
"""

from __future__ import annotations

import numpy as np

from magnetics.data.fetch.toksearch import Channel, _write_h5


def _write(tmp_path, channels):
    out = str(tmp_path / "shot.h5")
    return out, _write_h5(
        out, 123, "both", "test", channels, compression="lzf", tmin=None, tmax=None, stride=1
    )


def test_degenerate_time_axis_reclassified_not_crash(tmp_path):
    """A channel with data but a None/empty time axis must not crash the writer.

    This is the original bug: float(c.time[0]) on an object-dtype array holding
    None raised TypeError and killed the whole run after all fetching finished.
    """
    t = np.linspace(0.0, 10.0, 100)
    good = Channel("GOOD", t, np.ones(100, np.float32), ok=True)
    # data fetched ok=True, but dim_of came back empty -> object array of None
    bad = Channel("BAD", np.atleast_1d(np.asarray(None)), np.ones(50, np.float32), ok=True)

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
    nan_t = Channel("NAN", np.array([0.0, np.nan, 1.0]), np.ones(3, np.float32), ok=True)
    good = Channel("GOOD", np.linspace(0, 1, 3), np.ones(3, np.float32), ok=True)

    _, (got, missing) = _write(tmp_path, [none_t, empty_t, nan_t, good])

    assert {c.name for c in got} == {"GOOD"}
    assert {c.name for c in missing} == {"NONE", "EMPTY", "NAN"}


def test_identical_time_bases_deduped_and_hardlinked(tmp_path):
    """Channels sharing a time base store the vector once and hard-link to it."""
    t = np.linspace(0.0, 5.0, 64)
    chans = [Channel(f"CH{i}", t.copy(), np.full(64, i, np.float32), ok=True) for i in range(3)]

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
    chans = [Channel("A", ok=False, error="no data"), Channel("B", ok=False, error="no data")]
    out, (got, missing) = _write(tmp_path, chans)
    assert not got
    assert {c.name for c in missing} == {"A", "B"}


def test_legacy_pointname_written_under_canonical_id(tmp_path):
    """A channel fetched under a legacy pointname is relabeled to the canonical id
    (so downstream stays shot-agnostic) and records the queried name as an attr."""
    t = np.linspace(0.0, 1.0, 8)
    # the fetch loop already relabeled c.name -> canonical id; query_names carries
    # {canonical id -> queried (legacy) pointname}.
    c = Channel("MPID66M067", t, np.ones(8, np.float32), ok=True)
    out = str(tmp_path / "shot.h5")
    _write_h5(
        out,
        150000,
        "both",
        "test",
        [c],
        compression="lzf",
        tmin=None,
        tmax=None,
        stride=1,
        query_names={"MPID66M067": "MPID067U"},
    )

    import h5py

    with h5py.File(out, "r") as h5:
        assert "MPID66M067" in h5 and "MPID067U" not in h5  # keyed by canonical id
        assert h5["MPID66M067"].attrs["pointname"] == "MPID067U"
