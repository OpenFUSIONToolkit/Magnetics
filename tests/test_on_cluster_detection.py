"""On-cluster detection: don't SSH to the host you're already running on.

Running the GUI on a cluster work node (the NoMachine → gateway → omega flow)
sent the "remote" backend's ssh to omega.gat.com *from omega*. Where the node's
known_hosts lacks that entry, ssh blocks on the host-key prompt, and a server
process has no tty to answer it — the pull sat at 0% forever instead of failing.

These pin the detector's boundaries (a load-balanced submit node still counts;
the site gateway does NOT) and the dispatch downgrade that avoids the self-SSH.
"""

from __future__ import annotations

import os
import socket
from types import SimpleNamespace

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

    def test_on_cluster_prefers_toksearch_via_the_cluster_interpreter(self, monkeypatch, tmp_path):
        """The whole point: when the site conda env has toksearch, route the pull
        through it (native PTDATA) rather than the slow mdsthin/mdsip fallback.
        Regression for the fix where an on-cluster pull quietly used mdsip and ran
        ~17x slower than the laptop's remote pull, which had toksearch all along."""
        self._spy(monkeypatch)  # run_remote (ssh) must not fire
        monkeypatch.setattr(toksearch, "on_cluster_host", lambda device: True)

        from magnetics.data.fetch import remote as remote_run

        monkeypatch.setattr(remote_run, "cluster_python_has_toksearch", lambda py: True)
        # mdsthin must NOT be reached — that would be the slow fallback
        monkeypatch.setattr(
            toksearch,
            "_fetch_mdsthin",
            lambda *a, **k: pytest.fail("mdsthin used despite cluster toksearch"),
        )
        hit = {}

        def _fake_on_cluster(shot, analysis, **kw):
            hit["py"] = kw.get("python")
            return str(tmp_path / "o.h5")

        monkeypatch.setattr(remote_run, "run_on_cluster", _fake_on_cluster)

        out = toksearch.fetch_shot(
            184927,
            analysis="rotating",
            backend="remote",
            out=str(tmp_path / "o.h5"),
            progress=lambda f, m: None,
        )
        assert out == str(tmp_path / "o.h5")
        # it passed the device's configured cluster interpreter through
        assert hit.get("py") and "toksearch_env" in hit["py"]

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


class TestRunOnClusterIsolation:
    """run_on_cluster must expose ONLY the magnetics package to the cluster
    interpreter — never the venv site-packages, whose numpy/scipy are built for a
    different Python and shadow the conda env's copies (breaking `import
    toksearch`). This is the bug that made the first on-cluster attempt crash."""

    def test_pythonpath_is_an_isolated_package_symlink(self, monkeypatch, tmp_path):
        from magnetics.data.fetch import remote as remote_run

        captured = {}

        def _fake_run(argv, env=None, **kw):
            captured["env"] = env
            captured["pp"] = env.get("PYTHONPATH", "")
            # the symlink must exist AT RUN TIME (cleaned up in finally after)
            entries = os.listdir(captured["pp"])
            captured["entries"] = entries
            target = os.path.realpath(os.path.join(captured["pp"], "magnetics"))
            captured["target"] = target
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(remote_run.subprocess, "run", _fake_run)
        remote_run.run_on_cluster(
            184927, "rotating", python="/some/conda/env/bin/python", out=str(tmp_path / "o.h5")
        )

        pp = captured["pp"]
        # exactly the staging dir — NOT our site-packages (no numpy/scipy alongside)
        assert captured["entries"] == ["magnetics"], captured["entries"]
        assert "site-packages" not in pp
        # the symlink resolves to the real installed package
        assert captured["target"] == os.path.realpath(str(remote_run.PKG_ROOT))
        # and the stage is removed afterward (finally: shutil.rmtree)
        assert not os.path.exists(pp)

    def test_failure_raises_and_still_cleans_up(self, monkeypatch, tmp_path):
        from magnetics.data.fetch import remote as remote_run

        seen = {}

        def _fail_run(argv, env=None, **kw):
            seen["pp"] = env.get("PYTHONPATH")
            return SimpleNamespace(returncode=1)

        monkeypatch.setattr(remote_run.subprocess, "run", _fail_run)
        with pytest.raises(RuntimeError, match="on-cluster toksearch fetch failed"):
            remote_run.run_on_cluster(1, "both", python="/x/py", out=str(tmp_path / "o.h5"))
        assert not os.path.exists(seen["pp"])  # temp stage gone even on failure


class TestClusterPythonProbe:
    """The probe decides toksearch-vs-mdsthin, so a false negative silently costs
    ~5-7x on every on-cluster pull. The subprocess is the arbiter — don't
    pre-reject interpreters it would happily run."""

    def test_bare_command_name_is_resolved_through_path(self, monkeypatch):
        from magnetics.data.fetch import remote as remote_run

        # `Path("python3").exists()` is False anywhere but the cwd; PATH lookup
        # is what subprocess would do, so the probe must get a chance to run.
        monkeypatch.setattr(remote_run.shutil, "which", lambda p: "/opt/conda/bin/" + p)
        seen = {}

        def _probe(argv, **kw):
            seen["argv"] = argv
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(remote_run.subprocess, "run", _probe)
        assert remote_run.cluster_python_has_toksearch("python3")
        assert seen["argv"][0] == "/opt/conda/bin/python3"

    def test_absolute_path_is_passed_through_untouched(self, monkeypatch):
        from magnetics.data.fetch import remote as remote_run

        monkeypatch.setattr(
            remote_run.shutil, "which", lambda p: pytest.fail("which() on an absolute path")
        )
        seen = {}

        def _probe(argv, **kw):
            seen["argv"] = argv
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(remote_run.subprocess, "run", _probe)
        assert remote_run.cluster_python_has_toksearch("/fusion/env/bin/python")
        assert seen["argv"][0] == "/fusion/env/bin/python"

    def test_missing_interpreter_is_false_not_a_crash(self, monkeypatch):
        from magnetics.data.fetch import remote as remote_run

        monkeypatch.setattr(remote_run.shutil, "which", lambda p: None)

        def _enoent(argv, **kw):
            raise FileNotFoundError(argv[0])

        monkeypatch.setattr(remote_run.subprocess, "run", _enoent)
        assert not remote_run.cluster_python_has_toksearch("nope-python")

    def test_none_short_circuits_without_spawning(self, monkeypatch):
        from magnetics.data.fetch import remote as remote_run

        monkeypatch.setattr(
            remote_run.subprocess, "run", lambda *a, **k: pytest.fail("spawned for None")
        )
        assert not remote_run.cluster_python_has_toksearch(None)
