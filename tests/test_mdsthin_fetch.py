"""Offline tests for the DIII-D mdsthin fetch body (`_fetch_mdsthin`).

The getMany batching, its per-channel fallback, and the transport-vs-no-data
error classification are the guts of every laptop pull, but they only ran
against a live gateway before. A stub `mdsthin.Connection` (per-pointname
scripted responses) exercises them without a network; `tcp=True` skips the SSH
tunnel so no subprocess is spawned.
"""

from __future__ import annotations

import numpy as np
import pytest

import mdsthin

from magnetics.data.fetch import toksearch

T = np.linspace(0.0, 10.0, 50)
Y = np.ones(50, np.float32)


class _Desc:
    def __init__(self, arr):
        self._a = np.asarray(arr)

    def data(self):
        return self._a


class _StubGetMany:
    def __init__(self, conn):
        self.conn = conn
        self.named: dict[str, tuple[str, str]] = {}  # d0/t0 -> (pointname, expr)

    def append(self, name, expr, pt, shot):
        self.named[name] = (pt, expr)
        self.conn.exprs.append(expr)

    def execute(self):
        self.conn.getmany_execs += 1
        if self.conn.fail_batch:
            raise RuntimeError("getMany not supported by this server")

    def get(self, name):
        pt, _ = self.named[name]
        kind, *payload = self.conn.responses.get(pt, ("nodata",))
        if kind == "raise":
            raise payload[0]
        if kind == "nodata":
            return _Desc([0])  # ptdata2's no-data sentinel: length-1 [0]
        data, time = payload
        return _Desc(data if name.startswith("d") else time)


class _StubConn:
    """Scripted mdsthin connection. responses: pointname -> ("ok", data, time) |
    ("nodata",) | ("raise", exc). `fail_batch=True` makes getMany.execute raise,
    forcing the per-channel fallback."""

    def __init__(self, responses, fail_batch=False):
        self.responses = responses
        self.fail_batch = fail_batch
        self.exprs: list[str] = []
        self.getmany_execs = 0
        self.per_channel_calls = 0
        self._last_time = None

    def getMany(self):  # noqa: N802 (MDSplus API name)
        return _StubGetMany(self)

    def get(self, expr, *args):
        self.exprs.append(expr)
        if expr.startswith("_s = "):
            self.per_channel_calls += 1
            pt = args[0]
            kind, *payload = self.responses.get(pt, ("nodata",))
            if kind == "raise":
                raise payload[0]
            if kind == "nodata":
                self._last_time = None
                return _Desc([0])
            data, time = payload
            self._last_time = time
            return _Desc(data)
        if expr == "dim_of(_s)":
            return _Desc(self._last_time)
        raise AssertionError(f"unexpected TDI expr: {expr}")


def _fetch(monkeypatch, conn, pointnames, **kw):
    monkeypatch.setattr(mdsthin, "Connection", lambda addr: conn)
    defaults = dict(
        username="user",
        gateway=None,
        server="atlas.gat.com:8000",
        tcp=True,  # direct dial → no SSH tunnel subprocess
        tmin=1000.0,
        tmax=2000.0,
        stride=1,
        workers=1,
        batch_size=2,
        progress=lambda *a: None,
    )
    defaults.update(kw)
    return toksearch._fetch_mdsthin(184927, pointnames, **defaults)


def test_getmany_happy_path_batches_and_orders(monkeypatch):
    conn = _StubConn({p: ("ok", Y * i, T) for i, p in enumerate(["A", "B", "C"], 1)})
    out = _fetch(monkeypatch, conn, ["A", "B", "C"])
    # deterministic caller order regardless of batch/worker completion order
    assert [c.name for c in out] == ["A", "B", "C"]
    assert all(c.ok for c in out)
    np.testing.assert_array_equal(out[1].data, Y * 2)
    np.testing.assert_array_equal(out[0].time, T)
    # 3 channels at batch_size=2 → 2 getMany round trips, no per-channel calls
    assert conn.getmany_execs == 2
    assert conn.per_channel_calls == 0
    # the server-side reduction suffix is on every expression (window pushed remote)
    assert all("[1000.0 : 2000.0]" in e for e in conn.exprs if "ptdata2" in e)


def test_stride_appends_index_subscript(monkeypatch):
    conn = _StubConn({"A": ("ok", Y, T)})
    _fetch(monkeypatch, conn, ["A"], stride=4)
    assert any("[0 : * : 4]" in e for e in conn.exprs), conn.exprs


def test_no_data_channel_is_missing_with_no_data_kind(monkeypatch):
    conn = _StubConn({"A": ("ok", Y, T), "B": ("nodata",)})
    out = {c.name: c for c in _fetch(monkeypatch, conn, ["A", "B"])}
    assert out["A"].ok
    assert not out["B"].ok
    assert out["B"].error == "no data"
    assert out["B"].error_kind == "no_data"  # cacheable as missing


def test_per_channel_error_in_batch_is_classified(monkeypatch):
    conn = _StubConn(
        {
            "A": ("ok", Y, T),
            "B": ("raise", RuntimeError("Connection reset by peer")),
            "C": ("raise", RuntimeError("%TREE-W-NODATA, no data available")),
        }
    )
    out = {c.name: c for c in _fetch(monkeypatch, conn, ["A", "B", "C"], batch_size=3)}
    assert out["A"].ok
    # transport failure → retried next pull (issue #63); MDSplus no-data → cached
    assert out["B"].error_kind == "transport"
    assert out["C"].error_kind == "no_data"


def test_whole_batch_failure_falls_back_to_per_channel(monkeypatch):
    conn = _StubConn({p: ("ok", Y, T) for p in ["A", "B", "C"]}, fail_batch=True)
    out = _fetch(monkeypatch, conn, ["A", "B", "C"])
    assert [c.name for c in out] == ["A", "B", "C"]
    assert all(c.ok for c in out)
    # one failed getMany attempt, then everything through the 2-round-trip path —
    # and the fallback sticks for later batches (no second getMany attempt)
    assert conn.getmany_execs == 1
    assert conn.per_channel_calls == 3


def test_per_channel_mode_never_tries_getmany(monkeypatch):
    conn = _StubConn({"A": ("ok", Y, T)})
    out = _fetch(monkeypatch, conn, ["A"], per_channel=True)
    assert out[0].ok
    assert conn.getmany_execs == 0
    assert conn.per_channel_calls == 1


def test_progress_reaches_one_across_workers(monkeypatch):
    fracs = []
    conn = _StubConn({p: ("ok", Y, T) for p in "ABCDEF"})
    _fetch(
        monkeypatch,
        conn,
        list("ABCDEF"),
        workers=3,
        batch_size=1,
        progress=lambda f, m: fracs.append(f),
    )
    assert fracs and max(fracs) == pytest.approx(1.0)


def test_transport_failure_end_to_end_is_not_cached_as_missing(monkeypatch, tmp_path):
    """The #63 chain through the real writer: a batch whose connection died must
    leave the channel retryable — in the run report but NOT in channels_missing."""
    import h5py

    conn = _StubConn({"A": ("ok", Y, T), "B": ("raise", ConnectionResetError("reset"))})
    channels = _fetch(monkeypatch, conn, ["A", "B"])
    out = str(tmp_path / "shot.h5")
    toksearch._write_h5(
        out,
        184927,
        "rotating",
        "mdsthin",
        channels,
        compression="lzf",
        tmin=1000.0,
        tmax=2000.0,
        stride=1,
    )
    with h5py.File(out, "r") as h5:
        missing = {x.decode() for x in h5.attrs["channels_missing"]}
        fetched = {x.decode() for x in h5.attrs["channels_fetched"]}
    assert fetched == {"A"}
    assert missing == set()  # B is retryable, not poisoned into the cache
