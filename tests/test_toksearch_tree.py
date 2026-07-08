#!/usr/bin/env python3
"""Offline tests for the toksearch EFIT-tree fetch (no network/MDS deps).

The toksearch backend can't open EFIT trees locally on the cluster (the direct
interpreter runs without the MDSplus tree-path env), so tree signals like `kappa`
are fetched over a direct mdsip connection to the device server, reusing the
mdsthin path's ``openTree -> get`` logic. These tests cover the wrapper's graceful
degradation and the shared fetch logic with a stub connection.

Run:  uv run python -m pytest tests/test_toksearch_tree.py -q
"""

from __future__ import annotations

import sys
import types

import numpy as np

from magnetics.data.fetch.toksearch import _mdsthin_tree_channels, _toksearch_tree_channels


def _noop(_frac, _msg):
    pass


class _MapConn:
    """mdsip Connection stub with per-expression responses.

    ``responses`` maps an expression string (a node, or ``dim_of(node)``) to a
    numpy array, or to an ``Exception`` instance to raise from ``get``. Trees named
    in ``open_fail`` raise from ``openTree``. This models the axis production
    actually resolves candidates on -- which node/expr returns usable data -- so a
    two-candidate signal can express "candidate 1 fails / candidate 2 wins".
    """

    def __init__(self, responses, open_fail=()):
        self._responses = responses
        self._open_fail = set(open_fail)
        self.opened: list[tuple[str, int]] = []

    def openTree(self, tree, shot):  # noqa: N802 (MDSplus API name)
        if tree in self._open_fail:
            raise OSError(f"cannot open {tree}")
        self.opened.append((tree, shot))

    def get(self, expr):
        val = self._responses[expr]
        if isinstance(val, Exception):
            raise val
        return _StubNode(val)


def test_no_tree_signals_returns_empty():
    assert _toksearch_tree_channels(123, {}, "atlas.gat.com:8000", None, None, _noop) == []


def test_missing_server_degrades_to_not_ok_channels():
    # No server configured → clean not-ok channels, never a crash (the PTDATA pull
    # must still succeed even when the tree server is unknown).
    out = _toksearch_tree_channels(123, {"kappa": [("efit01", r"\kappa")]}, None, None, None, _noop)
    assert [(c.name, c.ok) for c in out] == [("kappa", False)]
    assert out[0].error == "no tree server configured"


class _StubNode:
    def __init__(self, arr):
        self._arr = arr

    def data(self):
        return self._arr


class _StubConn:
    """Minimal mdsip Connection: openTree is a no-op; get() serves data/time."""

    def __init__(self, data, time):
        self._data, self._time = data, time

    def openTree(self, tree, shot):  # noqa: N802 (MDSplus API name)
        pass

    def get(self, expr):
        return _StubNode(self._time if expr.startswith("dim_of(") else self._data)


def test_tree_fetch_reads_data_and_time_via_openTree_get():
    # The shared logic _toksearch_tree_channels delegates to: a working connection
    # yields an ok Channel with the fetched samples + time base.
    data = np.array([1.0, 1.4, 1.5], dtype=float)  # e.g. elongation κ(t)
    time = np.array([2000.0, 2500.0, 3000.0], dtype=float)
    out = _mdsthin_tree_channels(
        lambda: _StubConn(data, time),
        190000,
        {"kappa": [("efit01", r"\kappa")]},
        None,
        None,
        _noop,
    )
    assert len(out) == 1 and out[0].ok and out[0].name == "kappa"
    np.testing.assert_allclose(out[0].data, data)
    np.testing.assert_allclose(out[0].time, time)


# --- the wrapper's OWN body: host normalization + MDSplus/mdsthin import branch ---
# The tests above reach _toksearch_tree_channels only through its two early returns
# (empty tree_signals, server=None). These drive its real logic -- the server-string
# normalization and the `import MDSplus -> except ImportError -> mdsthin` connect
# closure -- by injecting a fake Connection, so a regression there can't stay green.


def test_wrapper_success_normalizes_host_and_uses_mdsplus_connection(monkeypatch):
    # server="mdsip://user@atlas.gat.com:8000" must normalize to the bare host:port,
    # and the `import MDSplus` branch must be used when MDSplus is importable.
    seen = {}
    data = np.array([1.0, 1.4, 1.5], dtype=float)
    time = np.array([2000.0, 2500.0, 3000.0], dtype=float)

    def _connection(host):
        seen["host"] = host
        return _MapConn({r"\kappa": data, r"dim_of(\kappa)": time})

    fake = types.ModuleType("MDSplus")
    fake.Connection = _connection
    monkeypatch.setitem(sys.modules, "MDSplus", fake)

    out = _toksearch_tree_channels(
        190000,
        {"kappa": [("efit01", r"\kappa")]},
        "mdsip://user@atlas.gat.com:8000",
        None,
        None,
        _noop,
    )
    assert seen["host"] == "atlas.gat.com:8000"  # split('://')[-1].split('@')[-1]
    assert len(out) == 1 and out[0].ok and out[0].name == "kappa"
    np.testing.assert_allclose(out[0].data, data)
    np.testing.assert_allclose(out[0].time, time)


def test_wrapper_falls_back_to_mdsthin_when_mdsplus_absent(monkeypatch):
    # On the cluster MDSplus may be unimportable; the closure must fall back to
    # mdsthin.Connection rather than raising. A None entry makes `import MDSplus`
    # raise ImportError (the documented sentinel), forcing the except branch.
    import mdsthin

    seen = {}
    data = np.array([1.0, 1.4, 1.5], dtype=float)
    time = np.array([2000.0, 2500.0, 3000.0], dtype=float)

    def _connection(host):
        seen["host"] = host
        return _MapConn({r"\kappa": data, r"dim_of(\kappa)": time})

    monkeypatch.setitem(sys.modules, "MDSplus", None)
    monkeypatch.setattr(mdsthin, "Connection", _connection)

    out = _toksearch_tree_channels(
        190000, {"kappa": [("efit01", r"\kappa")]}, "atlas.gat.com:8000", None, None, _noop
    )
    assert seen["host"] == "atlas.gat.com:8000"
    assert len(out) == 1 and out[0].ok and out[0].name == "kappa"


def test_wrapper_degrades_when_connection_raises(monkeypatch):
    # The whole point of the PR: atlas unreachable -> connect() raises -> one not-ok
    # Channel per signal (never a crash), so the already-fetched PTDATA pull survives.
    def _boom(host):
        raise ConnectionRefusedError("atlas unreachable")

    fake = types.ModuleType("MDSplus")
    fake.Connection = _boom
    monkeypatch.setitem(sys.modules, "MDSplus", fake)

    out = _toksearch_tree_channels(
        190000,
        {"kappa": [("efit01", r"\kappa")], "li": [("efit01", r"\li")]},
        "atlas.gat.com:8000",
        None,
        None,
        _noop,
    )
    assert [(c.name, c.ok) for c in out] == [("kappa", False), ("li", False)]
    assert all(c.error.startswith("tree server atlas.gat.com:8000:") for c in out)


# --- multi-candidate fallthrough: the path production ALWAYS uses -----------------
# _plasma_signal emits two ordered candidates for kappa (\kappa, then the aeqdsk
# fallback); the first fails on some shots. These prove "candidate 1 fails ->
# candidate 2 wins" for the get() and openTree failure modes.


def test_second_candidate_wins_when_first_returns_degenerate_data():
    # Candidate 1 (\kappa) returns a mismatched time base (degenerate); candidate 2
    # (the aeqdsk node) returns a clean pair and must win.
    good = np.array([1.0, 1.4, 1.5], dtype=float)
    time = np.array([2000.0, 2500.0, 3000.0], dtype=float)
    conn = _MapConn(
        {
            r"\kappa": good,
            r"dim_of(\kappa)": np.array([2000.0, 2500.0], dtype=float),  # size 2 != 3
            r"\top.results.aeqdsk:kappa": good,
            r"dim_of(\top.results.aeqdsk:kappa)": time,
        }
    )
    out = _mdsthin_tree_channels(
        lambda: conn,
        190000,
        {"kappa": [("efit01", r"\kappa"), ("efit01", r"\top.results.aeqdsk:kappa")]},
        None,
        None,
        _noop,
    )
    assert len(out) == 1 and out[0].ok and out[0].name == "kappa"
    np.testing.assert_allclose(out[0].data, good)
    np.testing.assert_allclose(out[0].time, time)


def test_second_candidate_wins_when_first_open_fails():
    # Candidate 1 lives in a tree that won't open; the loop must continue to
    # candidate 2 rather than giving up.
    good = np.array([1.0, 1.4, 1.5], dtype=float)
    time = np.array([2000.0, 2500.0, 3000.0], dtype=float)
    conn = _MapConn({r"\x": good, r"dim_of(\x)": time}, open_fail=["badtree"])
    out = _mdsthin_tree_channels(
        lambda: conn,
        190000,
        {"foo": [("badtree", r"\x"), ("goodtree", r"\x")]},
        None,
        None,
        _noop,
    )
    assert len(out) == 1 and out[0].ok and out[0].name == "foo"
    assert conn.opened == [("goodtree", 190000)]  # badtree open raised, was skipped
    np.testing.assert_allclose(out[0].data, good)


def test_all_candidates_degenerate_yields_not_ok_channel():
    # Every candidate returns an unusable (size-mismatched) pair -> not-ok Channel
    # tagged 'degenerate', never a silent ok with garbage.
    conn = _MapConn(
        {
            r"\kappa": np.array([1.0, 1.4, 1.5], dtype=float),
            r"dim_of(\kappa)": np.array([2000.0], dtype=float),  # size 1 != 3
        }
    )
    out = _mdsthin_tree_channels(
        lambda: conn, 190000, {"kappa": [("efit01", r"\kappa")]}, None, None, _noop
    )
    assert len(out) == 1 and not out[0].ok
    assert "degenerate" in out[0].error


def test_non_finite_time_base_is_rejected():
    # A NaN in the time base must fail the isfinite guard rather than pass through
    # to the HDF5 writer as a valid axis.
    conn = _MapConn(
        {
            r"\kappa": np.array([1.0, 1.4, 1.5], dtype=float),
            r"dim_of(\kappa)": np.array([2000.0, np.nan, 3000.0], dtype=float),
        }
    )
    out = _mdsthin_tree_channels(
        lambda: conn, 190000, {"kappa": [("efit01", r"\kappa")]}, None, None, _noop
    )
    assert len(out) == 1 and not out[0].ok
    assert "degenerate" in out[0].error


def test_window_trim_is_applied_to_tree_signal():
    # tmin/tmax must trim the tree signal client-side (EFIT time bases are coarse;
    # no decimation, window only).
    data = np.array([1.0, 1.4, 1.5], dtype=float)
    time = np.array([2000.0, 2500.0, 3000.0], dtype=float)
    conn = _MapConn({r"\kappa": data, r"dim_of(\kappa)": time})
    out = _mdsthin_tree_channels(
        lambda: conn,
        190000,
        {"kappa": [("efit01", r"\kappa")]},
        2400.0,  # tmin
        3000.0,  # tmax
        _noop,
    )
    assert len(out) == 1 and out[0].ok
    np.testing.assert_allclose(out[0].time, [2500.0, 3000.0])
    np.testing.assert_allclose(out[0].data, [1.4, 1.5])


def test_split_custom_signals_routes_efit_scalars_to_the_tree():
    """GUI custom signals: PTDATA pointnames stay PTDATA, but EFIT scalars named in
    the device's `derived signals` (betan, q95, …) route to the tree-fetch path with
    the AEQDSK-fallback node — otherwise ptdata2 returns nothing and they read back
    'missing' (the betan bug)."""
    from magnetics.data.devices import load_device
    from magnetics.data.fetch.toksearch import split_custom_signals

    dev = load_device("diiid")
    pts, trees = split_custom_signals(dev, ["Ip", "betan", "bt", "BETAN"])

    assert pts == ["Ip", "bt"]  # PTDATA, order-preserving + deduped
    assert "betan" in trees and "BETAN" in trees  # case-insensitive membership
    # the real node lives under the AEQDSK results path — must be a candidate
    assert ("efit01", r"\top.results.aeqdsk:betan") in trees["betan"]


def test_split_custom_signals_no_catalog_is_all_ptdata():
    """A device without a `derived signals` block routes everything to PTDATA."""
    from magnetics.data.fetch.toksearch import split_custom_signals

    pts, trees = split_custom_signals({}, ["ip", "betan"])
    assert pts == ["ip", "betan"] and trees == {}
