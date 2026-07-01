"""Offline (data-free, no-network) coverage of the NSTX/NSTX-U MDSplus-tree fetch.

The real path is exercised live in ``test_nstx_fetch_live.py`` (flux-gated). Here a
FAKE mdsthin ``Connection`` drives ``_fetch_mdsthin_tree`` and the ``fetch_shot`` tree
route so CI verifies the *logic* — gain/na scaling, seconds→ms conversion, the
value-window subscript, per-segment tree selection, device_id/geometry h5 attrs — with
no PPPL access and no committed tokamak data. All signals are fabricated.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

# ── a fake mdsthin.Connection: returns fabricated seconds-based signals ────────
_N = 128


class _Desc:
    def __init__(self, arr):
        self._a = arr

    def data(self):
        return self._a


class FakeConn:
    """Minimal mdsthin.Connection stand-in. `get(expr)` returns a constant signal;
    `get("dim_of(...)")` returns a matching SECONDS time base (0.20–0.30 s) so the
    fetch must convert it to ms. openTree records opens and rejects unknown trees."""

    RAW = 2.0
    known_trees = ("fastmag", "efit01")

    def __init__(self, *a, **k):
        self.opened: list[tuple[str, int]] = []

    def openTree(self, tree, shot):
        if tree not in self.known_trees:
            raise RuntimeError(f"%TREE-E-FILE_NOT_FOUND {tree}")
        self.opened.append((tree, int(shot)))

    def get(self, expr, *args):
        if str(expr).startswith("dim_of("):
            return _Desc(np.linspace(0.20, 0.30, _N).astype(np.float32))
        return _Desc(np.full(_N, self.RAW, dtype=np.float32))


@pytest.fixture
def fake_mdsthin(monkeypatch):
    mod = types.ModuleType("mdsthin")
    mod.Connection = FakeConn
    monkeypatch.setitem(sys.modules, "mdsthin", mod)
    return mod


def _dev():
    # Hand-made tree device: two sensors with distinct gain/na (one negative sign),
    # so the physical scaling raw*gain/na is unambiguous.
    return {
        "name": "FAKE-NSTX",
        "access": "mdsplus_tree",
        "gateway": "fakegw",
        "server": "fakehost:8501",
        "tree": "fastmag",
        "time_units": "s",
        "plasma pointnames": {},
        "sensor_sets": {"pair": {"type": "list", "sensors": [r"\A", r"\B"]}},
        "sensors": {
            r"\A": {
                "segments": [{"since_shot": 0, "phi": 10.0, "theta": 5.0, "gain": 2.0, "na": 0.5}]
            },
            r"\B": {
                "segments": [{"since_shot": 0, "phi": 20.0, "theta": 6.0, "gain": -1.0, "na": 0.25}]
            },
        },
    }


def test_tree_fetch_scales_and_converts(fake_mdsthin):
    from magnetics.data.fetch.toksearch import _fetch_mdsthin_tree

    dev = _dev()
    nodes = [r"\A", r"\B"]
    chans = _fetch_mdsthin_tree(
        1000,
        nodes,
        dev=dev,
        canonical_of={n: n for n in nodes},
        default_tree="fastmag",
        username=None,
        gateway=None,
        server="fakehost:8501",
        tcp=True,  # skip the SSH tunnel entirely
        tmin=250.0,
        tmax=270.0,
        time_units="s",
        progress=lambda *a: None,
        tree_signals={"ip": [("efit01", r"\IP")]},
    )
    by = {c.name: c for c in chans}

    # gain/na baked in: raw 2.0 * gain / na
    assert np.allclose(by[r"\A"].data, 2.0 * 2.0 / 0.5)  # +8.0
    assert np.allclose(by[r"\B"].data, 2.0 * -1.0 / 0.25)  # -8.0
    # seconds -> ms conversion on the time base (0.20–0.30 s -> 200–300 ms)
    t = by[r"\A"].time
    assert abs(t[0] - 200.0) < 1e-3 and abs(t[-1] - 300.0) < 1e-3
    assert t.size == by[r"\A"].data.size
    # plasma tree signal fetched from the second tree, also converted to ms
    assert by["ip"].ok and abs(by["ip"].time[0] - 200.0) < 1e-3


def test_tree_fetch_window_subscript_uses_native_seconds(fake_mdsthin):
    """The value-window subscript must be in the tree's native units (s), i.e.
    ms bounds / 1000 — not the raw ms numbers."""
    import magnetics.data.fetch.toksearch as tk

    seen: list[str] = []
    orig_get = FakeConn.get

    def spy(self, expr, *a):
        seen.append(str(expr))
        return orig_get(self, expr, *a)

    tk_conn = FakeConn
    tk_conn.get = spy
    try:
        tk._fetch_mdsthin_tree(
            1000,
            [r"\A"],
            dev=_dev(),
            canonical_of={r"\A": r"\A"},
            default_tree="fastmag",
            username=None,
            gateway=None,
            server="h:8501",
            tcp=True,
            tmin=250.0,
            tmax=270.0,
            time_units="s",
            progress=lambda *a: None,
        )
    finally:
        tk_conn.get = orig_get
    data_exprs = [e for e in seen if not e.startswith("dim_of(")]
    assert any("[0.25 : 0.27]" in e for e in data_exprs), data_exprs


def test_fetch_shot_tree_route_writes_device_id_and_geometry(fake_mdsthin, tmp_path, monkeypatch):
    """End-to-end through fetch_shot's tree route: device_id + per-channel geometry
    attrs + a tree `source` are written and read back."""
    import h5py

    from magnetics.data.fetch import toksearch as tk

    dev = _dev()
    monkeypatch.setattr(tk, "load_device", lambda name: dev)
    out = str(tmp_path / "shot_1000.h5")
    path = tk.fetch_shot(
        1000,
        device="fake-nstx",
        sensor_set="pair",  # tree route, our two nodes
        backend="mdsthin",
        tcp=True,
        # explicit server: the fake device isn't on disk, so the network-block
        # resolver (which loads the file directly) can't supply one.
        server="fakehost:8501",
        tmin=250.0,
        tmax=270.0,
        out=out,
    )
    with h5py.File(path, "r") as h5:
        assert h5.attrs["device_id"] == "fake-nstx"
        assert "tree" in str(h5.attrs["source"]).lower()
        assert set(k for k in h5.keys() if k != "_timebases") == {r"\A", r"\B"}
        gA = h5[r"\A"]
        # per-channel geometry attrs written from the shot-correct segment
        assert abs(gA.attrs["phi"] - 10.0) < 1e-6 and abs(gA.attrs["theta"] - 5.0) < 1e-6
        assert abs(gA.attrs["gain"] - 2.0) < 1e-6 and abs(gA.attrs["na"] - 0.5) < 1e-6
        # scaled + converted: raw 2.0 * 2.0/0.5 = 8.0, time 200–300 ms
        d = np.asarray(gA["data"][:])
        t = np.asarray(gA["time"][:])
        assert np.allclose(d, 8.0) and abs(t[0] - 200.0) < 1e-3


def test_tree_device_requires_sensor_set():
    """A tree device pulled without a sensor_set fails fast with a clear message
    (no analysis→signal map) instead of querying DIII-D pointnames at the tree.
    Uses the real nstx.json; raises before any network access."""
    from magnetics.data.fetch.toksearch import fetch_shot

    with pytest.raises(ValueError, match="sensor_set"):
        fetch_shot(204718, device="nstx", backend="mdsthin", tcp=True)


def test_tree_device_coerces_remote_to_mdsthin(monkeypatch):
    """A remote/toksearch request for a tree device is coerced to mdsthin (no
    cluster path) rather than SSHing to a nonexistent cluster. We stop right after
    coercion by requiring a sensor_set, so no network is touched."""
    from magnetics.data.fetch.toksearch import fetch_shot

    # remote would otherwise hit run_remote (cluster SSH); instead it must reach the
    # tree path's "needs a sensor_set" guard, proving the coercion ran.
    with pytest.raises(ValueError, match="sensor_set"):
        fetch_shot(204718, device="nstx", backend="remote", tcp=True)
