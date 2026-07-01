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

import numpy as np

from magnetics.data.fetch.toksearch import _mdsthin_tree_channels, _toksearch_tree_channels


def _noop(_frac, _msg):
    pass


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
