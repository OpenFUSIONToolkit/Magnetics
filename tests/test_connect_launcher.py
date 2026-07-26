"""magnetics-connect: the remote-GUI tunnel launcher, with ssh/subprocess faked.

The cluster round trip (NoMachine desktop -> gateway -> work node, or laptop ->
cluster) can't run offline, but everything the launcher does is command
construction + orchestration: the ControlMaster probe, the free-port handshake,
the single ssh that carries both the -L tunnel and the server process, readiness
polling through the tunnel, and teardown. These tests script all of it.
"""

from __future__ import annotations

import socket
import subprocess
import urllib.request
from types import SimpleNamespace

import pytest

from magnetics import connect

PROBED = "43211 omega-b.gat.com\n"


class _Run:
    """Record subprocess.run calls; script the probe's stdout/returncode."""

    def __init__(self, probe_stdout=PROBED, probe_rc=0):
        self.calls: list[list[str]] = []
        self.probe_stdout = probe_stdout
        self.probe_rc = probe_rc

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        joined = " ".join(str(c) for c in cmd)
        if "python3 -c" in joined:  # the free-port/node probe
            return SimpleNamespace(returncode=self.probe_rc, stdout=self.probe_stdout, stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def joined(self):
        return [" ".join(str(c) for c in call) for call in self.calls]


class _Popen:
    """The ssh carrying tunnel + server: stays 'alive' unless told otherwise."""

    instances: list["_Popen"] = []

    def __init__(self, cmd, **kw):
        self.cmd = list(cmd)
        self.stdout = iter(["INFO: Uvicorn running\r\n"])
        self.terminated = False
        self._poll_rc = None
        _Popen.instances.append(self)

    def poll(self):
        return self._poll_rc

    def wait(self, timeout=None):
        return 0

    def terminate(self):
        self.terminated = True


class _Resp:
    """Context-manager fake for urlopen (dunders must live on the TYPE)."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def harness(monkeypatch):
    """Fake run/Popen/urlopen/webbrowser; return the recorders."""
    _Popen.instances = []
    run = _Run()
    opened: list[str] = []
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", _Popen)
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=0: _Resp())
    monkeypatch.setattr(connect.webbrowser, "open", opened.append)
    # deterministic local port regardless of what's free on the test machine
    monkeypatch.setattr(connect, "pick_local_port", lambda preferred=None: 55555)
    return SimpleNamespace(run=run, opened=opened)


def test_happy_path_builds_probe_tunnel_and_serve(harness):
    rc = connect.main(["omega"])
    assert rc == 0
    cmds = harness.run.joined()

    # probe: ControlMaster established once; asks the remote for port + node
    probe = cmds[0]
    assert "ControlMaster=auto" in probe and "omega" in probe
    assert "python3 -c" in probe

    # serve: ONE ssh carries the forced pty, the tunnel, and the server command
    serve = " ".join(_Popen.instances[0].cmd)
    assert "-tt" in serve
    assert "ExitOnForwardFailure=yes" in serve
    assert "-L 55555:127.0.0.1:43211" in serve  # local port -> probed remote port
    assert "bash -lc" in serve
    assert "--port 43211" in serve  # substituted into the default remote cmd
    assert "--no-browser" in serve  # the REMOTE server must not open a browser

    # local browser opened on the tunnel entrance; master torn down at exit
    assert harness.opened == ["http://localhost:55555"]
    assert any("-O exit" in c for c in cmds)


def test_jump_flag_reaches_both_ssh_invocations(harness):
    connect.main(["u@omega.gat.com", "-J", "u@cybele.gat.com:2039"])
    assert "-J u@cybele.gat.com:2039" in harness.run.joined()[0]
    assert "-J u@cybele.gat.com:2039" in " ".join(_Popen.instances[0].cmd)


def test_no_browser_and_data_dir(harness):
    connect.main(["omega", "--no-browser", "--data-dir", "/cscratch/me/mag data"])
    assert harness.opened == []
    # the path is forwarded and survives re-quoting through `bash -lc` (spaces intact)
    assert "--data-dir" in _Popen.instances[0].cmd[-1]
    assert "mag data" in _Popen.instances[0].cmd[-1]
    # the helper quotes it so the remote shell sees ONE argument
    default = connect.default_remote_cmd("/cscratch/me/mag data")
    assert default.endswith("--data-dir '/cscratch/me/mag data'")


def test_custom_remote_cmd_port_placeholder(harness):
    connect.main(["flux", "--remote-cmd", "module load magnetics && magnetics --port {port}"])
    serve = " ".join(_Popen.instances[0].cmd)
    assert "module load magnetics && magnetics --port 43211" in serve
    assert serve.count("--port") == 1  # placeholder consumed, nothing appended


def test_probe_failure_exits_before_any_server(monkeypatch):
    _Popen.instances = []
    run = _Run(probe_rc=255)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", _Popen)
    assert connect.main(["omega"]) == 1
    assert _Popen.instances == []  # never tried to start the server


def test_server_never_ready_terminates_the_tunnel(harness, monkeypatch):
    def _refused(url, timeout=0):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", _refused)

    class _DeadPopen(_Popen):
        def __init__(self, cmd, **kw):
            super().__init__(cmd, **kw)
            self._poll_rc = 127  # remote command not found; ssh already exited

    monkeypatch.setattr(subprocess, "Popen", _DeadPopen)
    assert connect.main(["omega"]) == 1
    assert _Popen.instances[0].terminated
    assert harness.opened == []


class TestBootstrap:
    """The default remote command self-installs: fast path if magnetics is
    present, else ensure uv, else `uvx magnetics` (PyPI, provisions its own
    Python). This is the zero-touch hand-off for a fresh GA machine."""

    def test_three_tiers_in_order(self):
        cmd = connect.default_remote_cmd()
        # 1) fast path: use an installed magnetics before anything else
        fast = cmd.index("command -v magnetics")
        exec_installed = cmd.index("exec magnetics")
        # 2) ensure uv only if uvx is missing (root-free installer)
        ensure_uv = cmd.index("command -v uvx")
        assert "astral.sh/uv/install.sh" in cmd
        # 3) last resort: uvx provisions + runs from PyPI
        uvx = cmd.index("exec uvx magnetics")
        assert fast < exec_installed < ensure_uv < uvx

    def test_prepends_local_bin_to_path(self):
        # uv installs into ~/.local/bin; it must be on PATH for the uvx step
        assert "$HOME/.local/bin" in connect.default_remote_cmd()

    def test_install_from_becomes_uvx_from(self):
        url = "https://example.org/magnetics-0.1.0-py3-none-any.whl"
        cmd = connect.default_remote_cmd(install_from=url)
        assert f"uvx --from {url} magnetics" in cmd
        # no --from when unset (plain PyPI)
        assert "--from" not in connect.default_remote_cmd()

    def test_every_port_placeholder_is_resolved(self, harness):
        # {port} appears in BOTH the fast-path and uvx exec lines
        connect.main(["omega"])
        serve = " ".join(_Popen.instances[0].cmd)
        assert "{port}" not in serve
        assert serve.count("--port 43211") == 2  # installed path + uvx path

    def test_bootstrap_is_the_default_but_remote_cmd_bypasses_it(self, harness):
        connect.main(["omega", "--remote-cmd", "magnetics --port {port}"])
        serve = " ".join(_Popen.instances[0].cmd)
        assert "uvx" not in serve and "astral.sh" not in serve


class TestHelpers:
    def test_resolve_remote_cmd_appends_when_no_placeholder(self):
        assert connect.resolve_remote_cmd("magnetics --no-browser", 8123).endswith("--port 8123")

    def test_control_sock_sanitizes_target(self):
        sock = connect.control_sock("user@host.gat.com:2039")
        assert sock.startswith("/tmp/mc-") and ":" not in sock and "@" not in sock

    def test_pick_local_port_mirrors_free_preferred(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            free = s.getsockname()[1]
        assert connect.pick_local_port(free) == free

    def test_pick_local_port_falls_back_when_busy(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            busy = s.getsockname()[1]
            got = connect.pick_local_port(busy)
            assert got != busy and got > 0

    def test_wait_ready_true_on_http_error_response(self, monkeypatch):
        import urllib.error

        def _forbidden(url, timeout=0):
            raise urllib.error.HTTPError(url, 403, "forbidden", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
        child = SimpleNamespace(poll=lambda: None)
        assert connect._wait_ready("http://localhost:1", child, timeout=5)
