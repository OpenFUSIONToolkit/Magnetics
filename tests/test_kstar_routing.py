"""A device with its own transport (KSTAR: access=mdsplus_tree + a `connection`
block) must ALWAYS use that transport, never the remote/omega cluster path — even
when the caller/GUI selects backend="remote". Regression for the bug where a KSTAR
pull was sent to the GA `omega` ssh alias and failed with "SSH to the cluster failed".
"""

import pytest

from magnetics.data.fetch import kstar_transport, remote, toksearch


class _TransportHit(Exception):
    """Raised by the patched KSTAR transport — proves we reached the tree path."""


def _make_probes(monkeypatch):
    """Patch run_remote (omega) and the KSTAR transport with tracking sentinels."""
    called = {"remote": False, "transport": False}

    def fake_remote(*a, **k):
        called["remote"] = True
        raise AssertionError("run_remote (omega) should not be called here")

    def fake_session(*a, **k):
        called["transport"] = True
        raise _TransportHit()

    monkeypatch.setattr(remote, "run_remote", fake_remote)
    monkeypatch.setattr(kstar_transport, "session", fake_session)
    return called


def test_kstar_backend_remote_uses_vpn_transport_not_omega(monkeypatch, tmp_path):
    called = _make_probes(monkeypatch)
    # backend="remote" (the GUI default) must NOT route KSTAR to the cluster.
    with pytest.raises((_TransportHit, SystemExit)):
        toksearch.fetch_shot(
            42477,
            "rotating",
            device="kstar",
            backend="remote",
            sensor_set="mirnov_toroidal",
            tmin=2.0,
            tmax=2.1,
            out=str(tmp_path / "kstar.h5"),
            force=True,
        )
    assert called["remote"] is False, "KSTAR pull was routed to the omega cluster!"
    assert called["transport"] is True, "KSTAR pull did not use its VPN transport"


def test_diiid_backend_remote_still_uses_run_remote(monkeypatch, tmp_path):
    # DIII-D has no transport → backend="remote" must still orchestrate on the cluster.
    hit = {"remote": False}

    def fake_remote(*a, **k):
        hit["remote"] = True
        return str(tmp_path / "diiid.h5")

    monkeypatch.setattr(remote, "run_remote", fake_remote)
    toksearch.fetch_shot(
        184927,
        "rotating",
        device="diiid",
        backend="remote",
        tmin=1000,
        tmax=1050,
        out=str(tmp_path / "diiid.h5"),
        force=True,
    )
    assert hit["remote"] is True, "DIII-D remote pull no longer reaches run_remote"


# ---------------------------------------------------------------------------
# tree_signals (Ip / B_T / kappa) must be fetched on the KSTAR tree path, and a
# per-era pointname alias that collides with another sensor must not silently
# drop a channel. Both run fully offline against stub connections.
# ---------------------------------------------------------------------------

import numpy as np

from magnetics.data.fetch.toksearch import _fetch_mds_tree, _resolve_pointnames


class _DefaultConn:
    """Stub mdsthin connection: every get() returns a valid (data, DIM_OF) pair
    unless the expression is in `fail` (then it raises). Records expressions."""

    def __init__(self, fail=()):
        self.fail = set(fail)
        self.exprs = []
        self.opened = []

    def openTree(self, tree, shot):  # noqa: N802 (MDSplus API name)
        self.opened.append(tree)

    def get(self, expr):
        self.exprs.append(expr)
        if any(f in expr for f in self.fail):
            raise RuntimeError(f"TreeNNF: {expr}")

        class _R:
            @staticmethod
            def data():
                if expr.startswith("DIM_OF("):
                    return np.linspace(0.25, 0.35, 64)
                return np.ones(64, np.float32)

        return _R()


def test_tree_signals_are_fetched_on_the_kstar_path():
    """Regression: the _tree_transport branch never passed tree_signals to
    _fetch_mds_tree, so Ip/B_T/kappa were silently dropped for every KSTAR shot —
    absent from channels_fetched AND channels_missing — and helicity fell back to
    its default."""
    conn = _DefaultConn()
    channels = _fetch_mds_tree(
        12345,
        [("\\MC1T01", "\\MC1T01", "kstar", 1.0)],
        connect=lambda: conn,
        tmin=0.25,
        tmax=0.35,
        progress=lambda *_: None,
        tree_signals={
            "Ip": [("PCS_KSTAR", "\\PC:PCRC03*(-1)*(1e-6)")],
            "kappa": [("efitrt1", "\\kappa"), ("efitrt1", "\\top.results.aeqdsk:kappa")],
        },
    )
    by_name = {c.name: c for c in channels}
    assert by_name["Ip"].ok and by_name["kappa"].ok
    # tree time is seconds; stored time must be ms
    np.testing.assert_allclose(by_name["Ip"].time[0], 250.0)
    # plasma traces are window-SLICED, never resample()d onto the sensor µs grid
    ip_exprs = [e for e in conn.exprs if "PCRC03" in e and not e.startswith("DIM_OF")]
    assert ip_exprs == ["(\\PC:PCRC03*(-1)*(1e-6))[0.25 : 0.35]"]
    # the sensor still goes through resample()
    assert any(e.startswith("resample(\\MC1T01") for e in conn.exprs)


def test_tree_signal_candidate_fallback_and_missing_are_reported():
    conn = _DefaultConn(fail=("\\kappa",))  # first kappa candidate fails
    channels = _fetch_mds_tree(
        12345,
        [],
        connect=lambda: conn,
        tmin=None,
        tmax=None,
        progress=lambda *_: None,
        tree_signals={
            "kappa": [("efitrt1", "\\kappa"), ("efitrt1", "\\top.results.aeqdsk:kappa")],
            "B_T": [("PCS_KSTAR", "\\kappa_not_there")],  # also matches fail
        },
    )
    by_name = {c.name: c for c in channels}
    assert by_name["kappa"].ok  # second candidate won
    assert not by_name["B_T"].ok  # recorded as missing, not lost
    assert "B_T" in {c.name for c in channels if not c.ok}


def test_alias_collision_is_skipped_and_identity_wins():
    """Regression: kstar.json maps \\MC1T10 -> pointname \\MC1P03 (since shot 17377)
    while \\MC1P03 is itself in the pull; both fetched channels got relabeled to the
    same name and the HDF5 writer silently dropped one. The node must be queried
    once, the sensor literally named \\MC1P03 keeps it, and the alias is reported
    as skipped — in either request order."""
    dev = {
        "sensors": {
            "\\MC1P03": {"segments": [{"since_shot": 0, "phi": 10.0}]},
            "\\MC1T10": {
                "segments": [{"since_shot": 17377, "phi": 160.5, "pointname": "\\MC1P03"}]
            },
        }
    }
    for order in (["\\MC1T10", "\\MC1P03"], ["\\MC1P03", "\\MC1T10"]):
        query, canon, skipped = _resolve_pointnames(dev, order, 20000)
        assert query == ["\\MC1P03"], order
        assert canon == {"\\MC1P03": "\\MC1P03"}, order
        assert skipped == ["\\MC1T10"], order
