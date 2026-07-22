"""On-cluster detection: don't SSH to the host you're already running on.

Running the GUI on a cluster work node (the NoMachine → gateway → omega flow)
sent the "remote" backend's ssh to omega.gat.com *from omega*. Where the node's
known_hosts lacks that entry, ssh blocks on the host-key prompt, and a server
process has no tty to answer it — the pull sat at 0% forever instead of failing.

These pin the detector's boundaries (a load-balanced submit node still counts;
the site gateway does NOT) and the dispatch downgrade that avoids the self-SSH.
"""

from __future__ import annotations

import socket

import pytest

from magnetics.data.fetch import network, toksearch


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    """The env forces the answer; clear it so tests see the real logic."""
    monkeypatch.delenv("MAGNETICS_ON_CLUSTER", raising=False)
    monkeypatch.delenv("MAGNETICS_ON_NETWORK", raising=False)


def _as_host(monkeypatch, fqdn: str) -> None:
    monkeypatch.setattr(socket, "getfqdn", lambda: fqdn)


class TestOnClusterHost:
    @pytest.mark.parametrize(
        "fqdn",
        [
            "omega.gat.com",  # the configured address itself
            "omega-a.gat.com",  # load-balanced submit nodes — what you actually land on
            "omega-b.gat.com",
            "omega25.gat.com",  # worker nodes (no dash)
        ],
    )
    def test_cluster_nodes_are_detected(self, monkeypatch, fqdn):
        _as_host(monkeypatch, fqdn)
        assert network.on_cluster_host("diiid")

    def test_site_gateway_is_not_the_cluster(self, monkeypatch):
        # cybele is inside gat.com and reaches omega by ssh — from there the
        # remote backend is correct and must NOT be downgraded.
        _as_host(monkeypatch, "cybele.gat.com")
        assert not network.on_cluster_host("diiid")

    def test_off_site_laptop_is_not_the_cluster(self, monkeypatch):
        _as_host(monkeypatch, "my-laptop.local")
        assert not network.on_cluster_host("diiid")

    def test_same_short_name_off_site_does_not_count(self, monkeypatch):
        # on_site gating: a personal box named "omega" elsewhere is not the cluster
        _as_host(monkeypatch, "omega.home.example")
        assert not network.on_cluster_host("diiid")

    def test_env_override_forces_both_answers(self, monkeypatch):
        _as_host(monkeypatch, "my-laptop.local")
        monkeypatch.setenv("MAGNETICS_ON_CLUSTER", "1")
        assert network.on_cluster_host("diiid")
        monkeypatch.setenv("MAGNETICS_ON_CLUSTER", "0")
        _as_host(monkeypatch, "omega-a.gat.com")
        assert not network.on_cluster_host("diiid")

    def test_device_without_a_cluster_block_is_never_on_cluster(self, monkeypatch):
        _as_host(monkeypatch, "omega-a.gat.com")
        monkeypatch.setattr(network, "cluster_login", lambda d: {"host": None, "port": 22})
        assert not network.on_cluster_host("diiid")


class TestDispatchDowngrade:
    """`backend="remote"` on the cluster must fetch in-process, never via ssh."""

    def _spy(self, monkeypatch):
        calls = {"remote": 0}

        def _boom(*a, **k):
            calls["remote"] += 1
            raise AssertionError("run_remote must not be called from the cluster")

        from magnetics.data.fetch import remote as remote_run

        monkeypatch.setattr(remote_run, "run_remote", _boom)
        return calls

    def test_on_cluster_remote_never_sshes_and_falls_back_to_mdsthin(self, monkeypatch, tmp_path):
        """Without toksearch importable (the uv-tool install on omega), the pull
        downgrades to mdsthin rather than dialing itself over ssh."""
        self._spy(monkeypatch)
        monkeypatch.setattr(toksearch, "on_cluster_host", lambda device: True)

        seen = {}

        def _fake_mdsthin(shot, pointnames, **kw):
            seen["called"] = True
            return []

        monkeypatch.setattr(toksearch, "_fetch_mdsthin", _fake_mdsthin)

        def _fake_write(out, *a, **k):
            seen["wrote"] = out
            # (got, missing) — one fetched channel, or the empty-result guard trips
            return ["MPI66M307D"], []

        monkeypatch.setattr(toksearch, "_write_h5", _fake_write)

        notes: list[str] = []
        toksearch.fetch_shot(
            184927,
            analysis="rotating",
            backend="remote",
            out=str(tmp_path / "shot.h5"),
            progress=lambda f, m: notes.append(m),
        )
        assert seen.get("called"), "should have fetched in-process via mdsthin"
        assert any("already on the cluster" in n for n in notes)

    def test_off_cluster_remote_still_orchestrates_over_ssh(self, monkeypatch, tmp_path):
        """The laptop path is untouched — remote still means remote."""
        monkeypatch.setattr(toksearch, "on_cluster_host", lambda device: False)
        hit = {}

        def _fake_remote(shot, analysis, **kw):
            hit["shot"] = shot
            return str(tmp_path / "shot_184927.h5")

        from magnetics.data.fetch import remote as remote_run

        monkeypatch.setattr(remote_run, "run_remote", _fake_remote)
        toksearch.fetch_shot(
            184927,
            analysis="rotating",
            backend="remote",
            out=str(tmp_path / "shot_184927.h5"),
            progress=lambda f, m: None,
        )
        assert hit.get("shot") == 184927
