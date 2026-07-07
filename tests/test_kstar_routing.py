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
