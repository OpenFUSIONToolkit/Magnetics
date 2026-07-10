#!/usr/bin/env python3
"""
Offline tests for the HDF5 writer (no network/MDS deps).

The fetch backends need live GA/DIII-D access, but `_write_h5` is pure and
testable with synthetic Channel objects. Covers the regression where a channel
fetches data samples but comes back with a degenerate time axis.

Run:  uv run python -m pytest tests/test_toksearch_writer.py -q
"""

from __future__ import annotations

import sys
import types

import numpy as np

from magnetics.data.fetch import toksearch
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


def test_toksearch_records_tree_signal_missing_when_tree_server_unavailable(monkeypatch):
    class FakePipeline:
        def __init__(self, shots):
            self.shots = shots
            self.fetches = []

        def fetch(self, key, signal):
            self.fetches.append((key, signal))

        def compute_serial(self):
            return [
                {
                    "errors": {},
                    "PT": {
                        "data": np.array([1.0, 2.0], dtype=float),
                        "times": np.array([0.0, 1.0], dtype=float),
                    },
                }
            ]

    fake_toksearch = types.ModuleType("toksearch")
    fake_toksearch.Pipeline = FakePipeline
    fake_toksearch.PtDataSignal = lambda name: ("pt", name)
    monkeypatch.setitem(sys.modules, "toksearch", fake_toksearch)
    monkeypatch.delitem(sys.modules, "toksearch_d3d", raising=False)

    channels = toksearch._fetch_toksearch(
        123,
        ["PT"],
        tmin=None,
        tmax=None,
        stride=1,
        progress=lambda *_: None,
        tree_signals={"kappa": [("efit01", "\\kappa")]},
    )

    by_name = {ch.name: ch for ch in channels}
    assert by_name["PT"].ok is True
    assert by_name["kappa"].ok is False
    assert by_name["kappa"].error == "no tree server configured"


# ---------------------------------------------------------------------------
# _merge_h5_files — the remote-backend result must fold into an existing file
# ---------------------------------------------------------------------------


def test_merge_h5_files_preserves_existing_channels(tmp_path):
    """Regression: a remote pull used to rsync the cluster file OVER the local shot
    file, so a one-signal custom pull (e.g. 'betan') destroyed every previously
    fetched channel. The staged file must merge in, replacing on name conflicts and
    keeping everything else."""
    import h5py

    from magnetics.data.fetch.toksearch import _merge_h5_files

    t = np.linspace(0.0, 10.0, 100)
    a = Channel("MPI66M307D", t, np.ones(100, np.float32), ok=True)
    b = Channel("MPI66M340D", t, np.full(100, 2.0, np.float32), ok=True)
    dst, _ = _write(tmp_path, [a, b])

    stage = tmp_path / "stage"
    stage.mkdir()
    src = str(stage / "shot.h5")
    t2 = np.linspace(0.0, 10.0, 50)
    new = Channel("betan", t2, np.full(50, 1.5, np.float32), ok=True)
    refetch = Channel("MPI66M340D", t, np.full(100, 9.0, np.float32), ok=True)
    gone = Channel("ip", ok=False, error="no data")
    _write_h5(
        src,
        123,
        "custom",
        "toksearch",
        [new, refetch, gone],
        compression="lzf",
        tmin=None,
        tmax=None,
        stride=1,
    )

    _merge_h5_files(src, dst)

    with h5py.File(dst, "r") as h5:
        # pre-existing channel untouched, re-fetched channel replaced, new one added
        assert set(h5) >= {"MPI66M307D", "MPI66M340D", "betan"}
        np.testing.assert_array_equal(h5["MPI66M307D/data"][()], 1.0)
        np.testing.assert_array_equal(h5["MPI66M340D/data"][()], 9.0)
        np.testing.assert_array_equal(h5["betan/data"][()], 1.5)
        np.testing.assert_allclose(h5["betan/time"][()], t2)
        fetched = {x.decode() for x in h5.attrs["channels_fetched"]}
        missing = {x.decode() for x in h5.attrs["channels_missing"]}
        assert {"MPI66M307D", "MPI66M340D", "betan"} <= fetched
        assert missing == {"ip"}
        # both selection labels recorded
        assert "custom" in str(h5.attrs["analysis"])


def test_fetch_shot_remote_merges_instead_of_clobbering(tmp_path, monkeypatch):
    """End-to-end dispatch regression: fetch_shot(backend='remote') with an existing
    compatible shot file must stage the cluster result and merge it — the local file
    keeps its earlier channels."""
    import h5py

    # existing local file with one 'earlier pull' channel, default window/stride
    out = tmp_path / "shot_184927.h5"
    t = np.linspace(0.0, 10.0, 100)
    _write_h5(
        str(out),
        184927,
        "both",
        "toksearch",
        [Channel("MPI66M307D", t, np.ones(100, np.float32), ok=True)],
        compression="lzf",
        tmin=None,
        tmax=None,
        stride=1,
    )

    def fake_run_remote(shot, analysis="both", *, local_out_dir=None, progress=None, **kw):
        # the cluster always writes a FRESH file with only the requested selection
        path = str(f"{local_out_dir}/shot_{shot}.h5")
        import os

        os.makedirs(local_out_dir, exist_ok=True)
        t2 = np.linspace(0.0, 10.0, 50)
        _write_h5(
            path,
            int(shot),
            "custom",
            "toksearch",
            [Channel("betan", t2, np.full(50, 1.5, np.float32), ok=True)],
            compression="lzf",
            tmin=None,
            tmax=None,
            stride=1,
        )
        return path

    from magnetics.data.fetch import remote as remote_mod

    monkeypatch.setattr(remote_mod, "run_remote", fake_run_remote)

    result = toksearch.fetch_shot(184927, backend="remote", raw_pointnames=["betan"], out=str(out))

    assert result == str(out)
    with h5py.File(out, "r") as h5:
        assert "MPI66M307D" in h5, "remote pull clobbered the existing channel"
        assert "betan" in h5
    assert not (tmp_path / "_remote_stage" / "shot_184927.h5").exists()
