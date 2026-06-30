"""Lazy windowed HDF5 reads must equal full-read-then-slice for every timebase the
fetcher can produce — a uniform shared clock and a distinct nonuniform clock —
across open/closed bounds and strides, and the node stack must stay float32.

Drives ``h5source`` through real files written by ``synthetic_h5`` (the fetcher's
on-disk layout), pointing ``MAGNETICS_DATA_DIR`` at a per-test tmp dir so the
on-disk shot index resolves. Equivalence is proven against an independently
computed reference (full read, then the same ``searchsorted`` slice), so the tests
assert observable values/dtype rather than the implementation.
"""
from __future__ import annotations

import numpy as np
import pytest

from magnetics.data import h5source
from magnetics.service import nodes

from tests import synthetic_h5

# A dense toroidal array on one shared uniform clock + one nonuniform-clock channel,
# so a single file exercises both the shared-link timebase and a distinct one.
PHIS = np.linspace(0.0, 330.0, 12)
UNIFORM_NAME = "MPID66M000"  # first generated rotating-array name (phi=0)
NONUNIFORM_NAME = "MPI_NONUNIFORM"


class _RecordingTimeDataset:
    def __init__(self, values):
        self._values = np.asarray(values)
        self.shape = self._values.shape
        self.reads = []

    def __getitem__(self, key):
        self.reads.append(key)
        return self._values[key]


@pytest.fixture()
def shot(tmp_path, monkeypatch):
    """Write one synthetic shot, point h5source at it, refresh its index; yield shot id."""
    channels, _t, _phis = synthetic_h5.rotating_array(
        PHIS, n=2, f_khz=8.0, fs_khz=500.0, dur_ms=40.0)
    channels.append(synthetic_h5.nonuniform_channel(NONUNIFORM_NAME, n_samples=3000))
    shot_id = 164672
    synthetic_h5.write_shot(tmp_path / "synthetic.h5", channels, shot=shot_id)
    monkeypatch.setenv("MAGNETICS_DATA_DIR", str(tmp_path))
    h5source.refresh()
    yield str(shot_id)
    h5source.refresh()


def _reference_slice(time_full, tmin_ms, tmax_ms, stride):
    """The spec for a window: indices the lazy read must reproduce exactly."""
    n = time_full.size
    i0 = 0 if tmin_ms is None else int(np.searchsorted(time_full, tmin_ms, "left"))
    i1 = n if tmax_ms is None else int(np.searchsorted(time_full, tmax_ms, "right"))
    return slice(i0, i1, stride)


# ── (a) uniform shared-clock window ──────────────────────────────────────────
def test_uniform_window_equals_full_slice(shot):
    t_full, d_full = h5source.load_channel(shot, UNIFORM_NAME)
    tmin, tmax = float(t_full[37]), float(t_full[1900])
    tw, dw = h5source.load_channel_window(shot, UNIFORM_NAME, tmin, tmax)
    sl = _reference_slice(t_full, tmin, tmax, 1)
    np.testing.assert_array_equal(tw, t_full[sl])
    np.testing.assert_array_equal(dw, d_full[sl])
    assert tw.dtype == np.float64 and dw.dtype == np.float32
    assert dw.size < d_full.size  # a real window, not the whole channel


# ── (b) nonuniform-clock window ──────────────────────────────────────────────
def test_nonuniform_window_equals_full_slice(shot):
    t_full, d_full = h5source.load_channel(shot, NONUNIFORM_NAME)
    # bounds between samples, where uniform-clock index math would be wrong
    tmin = float((t_full[200] + t_full[201]) / 2.0)
    tmax = float((t_full[1500] + t_full[1501]) / 2.0)
    tw, dw = h5source.load_channel_window(shot, NONUNIFORM_NAME, tmin, tmax)
    sl = _reference_slice(t_full, tmin, tmax, 1)
    np.testing.assert_array_equal(tw, t_full[sl])
    np.testing.assert_array_equal(dw, d_full[sl])
    assert tw.min() >= tmin and tw.max() <= tmax  # exact inclusive bounds


# ── (c) open bounds == full read ─────────────────────────────────────────────
def test_open_bounds_equal_full_read(shot):
    t_full, d_full = h5source.load_channel(shot, UNIFORM_NAME)
    tw, dw = h5source.load_channel_window(shot, UNIFORM_NAME)  # both bounds open
    np.testing.assert_array_equal(tw, t_full)
    np.testing.assert_array_equal(dw, d_full)
    # half-open: only an upper bound
    tmax = float(t_full[500])
    tw2, dw2 = h5source.load_channel_window(shot, UNIFORM_NAME, tmax_ms=tmax)
    sl = _reference_slice(t_full, None, tmax, 1)
    np.testing.assert_array_equal(dw2, d_full[sl])


# ── (d) stride > 1 ───────────────────────────────────────────────────────────
def test_stride_window_equals_full_slice(shot):
    t_full, d_full = h5source.load_channel(shot, UNIFORM_NAME)
    tmin, tmax = float(t_full[10]), float(t_full[1234])
    tw, dw = h5source.load_channel_window(shot, UNIFORM_NAME, tmin, tmax, stride=7)
    sl = _reference_slice(t_full, tmin, tmax, 7)
    np.testing.assert_array_equal(tw, t_full[sl])
    np.testing.assert_array_equal(dw, d_full[sl])


def test_resolve_slice_does_not_materialize_full_time_axis():
    """Bounded windows use scalar binary search, not ``time[:]``."""
    time = np.cumsum(np.linspace(0.1, 0.5, 4096))
    ds = _RecordingTimeDataset(time)
    tmin = float((time[777] + time[778]) / 2.0)
    tmax = float((time[1999] + time[2000]) / 2.0)

    sl = h5source._resolve_slice(ds, tmin, tmax, stride=5)
    expected = _reference_slice(time, tmin, tmax, 5)

    assert (sl.start, sl.stop, sl.step) == (expected.start, expected.stop, expected.step)
    assert slice(None, None, None) not in ds.reads
    assert len(ds.reads) <= 2 * int(np.ceil(np.log2(time.size)) + 1)


def test_resolve_slice_open_bounds_do_not_touch_time_axis():
    ds = _RecordingTimeDataset(np.arange(128, dtype=np.float64))
    sl = h5source._resolve_slice(ds, None, None, stride=3)
    assert (sl.start, sl.stop, sl.step) == (0, 128, 3)
    assert not ds.reads


def test_load_data_window_matches_channel_window(shot):
    """The data-only window equals the data half of the (time, data) window."""
    tmin, tmax = 5.0, 25.0
    _tw, dw = h5source.load_channel_window(shot, UNIFORM_NAME, tmin, tmax, stride=3)
    d_only = h5source.load_data_window(shot, UNIFORM_NAME, tmin, tmax, stride=3)
    np.testing.assert_array_equal(d_only, dw)
    assert d_only.dtype == np.float32


def test_load_window_stack_one_open_equals_per_channel(shot):
    """Batch stack read (one file open) == per-channel reads on the shared clock."""
    names = [f"MPID66M{int(round(p)) % 360:03d}" for p in PHIS]
    t0, datas = h5source.load_window_stack(shot, names)
    t_ref, _ = h5source.load_channel(shot, names[0])
    np.testing.assert_array_equal(t0, t_ref)
    assert len(datas) == len(names)
    for nm, d in zip(names, datas):
        np.testing.assert_array_equal(d, h5source.load_data(shot, nm))
        assert d.dtype == np.float32


def test_window_stack_honors_window(shot):
    names = [f"MPID66M{int(round(p)) % 360:03d}" for p in PHIS]
    t_full, _ = h5source.load_channel(shot, names[0])
    tmin, tmax = float(t_full[100]), float(t_full[900])
    t0, datas = h5source.load_window_stack(shot, names, tmin, tmax, stride=2)
    sl = _reference_slice(t_full, tmin, tmax, 2)
    np.testing.assert_array_equal(t0, t_full[sl])
    for nm, d in zip(names, datas):
        np.testing.assert_array_equal(d, h5source.load_data(shot, nm)[sl])


# ── nodes._stack stays float32 (time stays float64) ──────────────────────────
def test_stack_returns_float32(shot):
    names = [f"MPID66M{int(round(p)) % 360:03d}" for p in PHIS]
    t, mat = nodes._stack(shot, names)
    assert mat.dtype == np.float32
    assert t.dtype == np.float64
    assert mat.shape[0] == len(names)
    # exact: the matrix is the per-channel float32 reads truncated to common length
    full = [h5source.load_data(shot, nm) for nm in names]
    nmin = min(d.size for d in full)
    expected = np.array([d[:nmin] for d in full], dtype=np.float32)
    np.testing.assert_array_equal(mat, expected)


# ── the window actually materializes fewer bytes (bounded-RAM regression) ────
def test_window_materializes_less_memory(shot):
    """A windowed read returns only the window's bytes — the bounded-RAM property.

    ``nbytes`` of the returned array is the deterministic measure of what was
    materialized (numpy data buffers live outside ``tracemalloc``, so the array
    size, not the Python heap, is the honest signal here).
    """
    t_full, d_full = h5source.load_channel(shot, UNIFORM_NAME)
    tmin, tmax = float(t_full[0]), float(t_full[t_full.size // 4])
    _tw, d_win = h5source.load_channel_window(shot, UNIFORM_NAME, tmin, tmax)
    # ~a quarter of the samples => roughly a quarter of the materialized bytes
    assert d_win.nbytes < d_full.nbytes // 3
