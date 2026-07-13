"""run_remote's SSH/rsync command construction, with subprocess faked.

The cluster round-trip can't run offline, but every command it builds is pure
logic — and it has already burned us once (the remote result clobbering the
local shot file). These tests script `subprocess.run` and assert the exact
orchestration: master connect + jump selection, per-user /tmp staging, the
remote fetch argv, the rsync copy-back target, cleanup, and teardown.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from magnetics.data.fetch import remote


class _Runner:
    """Record every subprocess.run; script per-command return codes/stdout."""

    def __init__(self, fail_on=None):
        self.calls: list[list[str]] = []
        self.fail_on = fail_on  # substring of the joined argv that should fail

    def __call__(self, cmd, env=None, **kw):
        self.calls.append(list(cmd))
        joined = " ".join(str(c) for c in cmd)
        rc = 1 if (self.fail_on and self.fail_on in joined) else 0
        stdout = "gauser\n" if "id -un" in joined else ""
        return SimpleNamespace(returncode=rc, stdout=stdout, stderr="")

    def joined(self):
        return [" ".join(str(c) for c in call) for call in self.calls]


@pytest.fixture()
def runner(monkeypatch):
    r = _Runner()
    monkeypatch.setattr(subprocess, "run", r)
    monkeypatch.setattr(remote, "on_site_network", lambda device: False)  # laptop
    return r


def test_off_site_pull_builds_the_full_round_trip(runner, tmp_path):
    out = remote.run_remote(
        184927,
        "both",
        username="myuser",
        tmin=1000,
        tmax=2000,
        decimate=1,
        device="diiid",
        local_out_dir=str(tmp_path),
    )
    cmds = runner.joined()

    # 1) one authenticated master with the site gateway as ProxyJump
    master = cmds[0]
    assert "ControlMaster=auto" in master and "myuser@omega.gat.com" in master
    assert "-J myuser@cybele.gat.com:2039" in master

    # 2) per-user /tmp stage (shared login node) + code sync via the master
    assert any("mkdir -p" in c and "/tmp/magnetics_out_myuser" in c for c in cmds)
    rsync_up = next(c for c in cmds if c.startswith("rsync") and "magnetics" in c)
    assert "myuser@omega.gat.com:~/magnetics_fetch/" in rsync_up

    # 3) the remote fetch runs THIS package with the toksearch backend and the
    #    caller's window, staging into the per-user /tmp file
    fetch = next(c for c in cmds if "-m magnetics.data.fetch.toksearch" in c)
    for frag in (
        "--backend toksearch",
        "--shot 184927",
        "--analysis both",
        "--tmin 1000",
        "--tmax 2000",
        "--out /tmp/magnetics_out_myuser/shot_184927.h5",
    ):
        assert frag in fetch, f"{frag!r} missing from: {fetch}"
    assert "--decimate" not in fetch  # decimate=1 is the default, don't forward it

    # 4) the result is rsync'd back to the REQUESTED local dir, the stage removed,
    #    and the ControlMaster torn down
    rsync_back = next(c for c in cmds if c.startswith("rsync") and str(tmp_path) in c)
    assert "myuser@omega.gat.com:/tmp/magnetics_out_myuser/shot_184927.h5" in rsync_back
    assert any("rm -f" in c and "shot_184927.h5" in c for c in cmds)
    assert "-O exit" in cmds[-1]
    assert out == str(tmp_path / "shot_184927.h5")


def test_custom_pointnames_replace_analysis_selection(runner, tmp_path):
    remote.run_remote(
        1, "both", username="u", raw_pointnames=["betan", "li"], local_out_dir=str(tmp_path)
    )
    fetch = next(c for c in runner.joined() if "-m magnetics.data.fetch.toksearch" in c)
    assert "--pointnames betan,li" in fetch
    assert "--analysis" not in fetch and "--sensor-set" not in fetch


def test_sensor_set_overrides_analysis(runner, tmp_path):
    remote.run_remote(1, "rotating", username="u", sensor_set="Bp All", local_out_dir=str(tmp_path))
    fetch = next(c for c in runner.joined() if "-m magnetics.data.fetch.toksearch" in c)
    assert (
        "--sensor-set 'Bp All'" in fetch
        or '--sensor-set "Bp All"' in fetch
        or "--sensor-set Bp All" in fetch
    )
    assert "--analysis" not in fetch


def test_on_site_drops_the_jump(monkeypatch, tmp_path):
    r = _Runner()
    monkeypatch.setattr(subprocess, "run", r)
    monkeypatch.setattr(remote, "on_site_network", lambda device: True)
    remote.run_remote(1, "both", username="u", local_out_dir=str(tmp_path))
    assert "-J" not in r.joined()[0]


def test_explicit_empty_jump_uses_alias_proxyjump(runner, tmp_path):
    # jump="" means "my ssh-config alias carries its own ProxyJump" — forcing -J
    # on top would double-jump.
    remote.run_remote(1, "both", host="myalias", jump="", local_out_dir=str(tmp_path))
    assert "-J" not in runner.joined()[0]


def test_unknown_user_is_resolved_on_the_cluster(runner, tmp_path):
    # no username: an ssh-config alias supplies it, so the stage-dir owner is
    # asked from the cluster (`id -un`, works with $USER unset in command shells)
    remote.run_remote(1, "both", local_out_dir=str(tmp_path))
    cmds = runner.joined()
    assert any("id -un" in c for c in cmds)
    assert any("/tmp/magnetics_out_gauser" in c for c in cmds)


def test_failed_master_connect_exits_before_any_sync(monkeypatch, tmp_path):
    r = _Runner(fail_on="true")  # the master probe command ends in `true`
    monkeypatch.setattr(subprocess, "run", r)
    monkeypatch.setattr(remote, "on_site_network", lambda device: False)
    with pytest.raises(SystemExit):
        remote.run_remote(1, "both", username="u", local_out_dir=str(tmp_path))
    # nothing was synced or executed remotely after the failed connect
    assert not any("rsync" in c for c in r.joined())


def test_unsafe_remote_dir_rejected_before_any_ssh(monkeypatch, tmp_path):
    r = _Runner()
    monkeypatch.setattr(subprocess, "run", r)
    with pytest.raises(ValueError, match="unsafe remote_dir"):
        remote.run_remote(1, "both", remote_dir="~/x; rm -rf /", local_out_dir=str(tmp_path))
    assert r.calls == []
