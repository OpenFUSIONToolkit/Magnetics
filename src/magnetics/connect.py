#!/usr/bin/env python3
"""One-command remote GUI: run the magnetics server on a cluster, browse it locally.

The problem this solves: the server must run where the data lives (omega, a PPPL
cluster, ...), but the browser lives somewhere else -- a NoMachine desktop on the
site gateway, or a laptop off-site -- and 127.0.0.1 there is not 127.0.0.1 here.
Rather than X-forwarding a browser across the firewall, this does the standard
SSH tunnel dance in one command:

  1. open one authenticated SSH master to HOST (ProxyJump'd when given);
  2. ask the remote for a free loopback port and its real node name (submit
     nodes are load-balanced -- "omega" may land you on omega-a or omega-b);
  3. start the server there, bound to 127.0.0.1 only, with the tunnel
     (``-L local:127.0.0.1:remote``) carried by the same connection;
  4. poll through the tunnel until the server answers, then open the local
     browser at ``http://localhost:<port>``.

Only HTTP crosses the wire -- fetches and fits run on the cluster, plots stream
back. Ctrl-C tears everything down (the forced remote pty SIGHUPs the server,
so nothing is orphaned on the shared node).

This file is deliberately STDLIB-ONLY and self-contained so it also runs where
magnetics is not installed (e.g. a gateway node with only system python3):

    scp src/magnetics/connect.py gateway:
    python3 connect.py omega

With the package installed it is simply ``magnetics-connect``.

Examples:
    magnetics-connect omega                       # ~/.ssh/config alias, key auth
    magnetics-connect pharrm@omega.gat.com -J pharrm@cybele.gat.com:2039
    magnetics-connect omega --data-dir /cscratch/$USER/magnetics
    magnetics-connect flux --remote-cmd \\
        'module load magnetics && magnetics --no-browser --port {port}'
"""

from __future__ import annotations

import argparse
import collections
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# The PyPI package + console-script the server ships as. Once published,
# `uvx magnetics` fetches it and provisions its own Python — nothing to install
# by hand. Until then, the bootstrap's fast path uses an already-installed
# `magnetics` (or point --install-from at a wheel).
PACKAGE = "magnetics"
# The root-free, official uv installer. omega/cybele have curl + outbound net;
# it drops uv in ~/.local/bin without touching the system.
UV_INSTALLER = "https://astral.sh/uv/install.sh"

# One remote python3 -c: print a free loopback port and the node's real name.
_PROBE_PY = (
    'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); '
    "print(s.getsockname()[1], socket.getfqdn())"
)


def _ctl_opts(sock: str) -> list[str]:
    """ControlMaster options: authenticate once, reuse for the serve connection."""
    return ["-o", "ControlMaster=auto", "-o", f"ControlPath={sock}", "-o", "ControlPersist=60"]


def control_sock(target: str) -> str:
    """Short per-target ControlPath in /tmp (macOS socket-path length limit)."""
    tag = "".join(c if (c.isalnum() or c in "._-") else "_" for c in target)
    return f"/tmp/mc-{tag}.sock"


def _serve_args(data_dir: str | None) -> str:
    """The `magnetics` server flags shared by every launch path. `{port}` is a
    placeholder resolved later (it appears more than once in the bootstrap)."""
    args = "--no-browser --port {port}"
    if data_dir:
        args += " --data-dir " + shlex.quote(data_dir)
    return args


def default_remote_cmd(data_dir: str | None = None, install_from: str | None = None) -> str:
    """A self-bootstrapping serve command (POSIX sh, run via ``bash -lc``).

    In order: run an already-installed ``magnetics`` if the remote has one (fast
    path, no install); else ensure ``uv`` (fetch the root-free installer if it is
    missing); else launch with ``uvx``, which downloads the package and provisions
    a suitable Python — omega's system Python is far too old, and uvx sidesteps
    that. ``install_from`` (a wheel URL / path / any uv source) overrides the PyPI
    default via ``uvx --from`` — the shim until the package is published.
    """
    serve = _serve_args(data_dir)
    from_opt = ("--from " + shlex.quote(install_from) + " ") if install_from else ""
    return (
        'export PATH="$HOME/.local/bin:$PATH"; '
        f"if command -v {PACKAGE} >/dev/null 2>&1; then exec {PACKAGE} {serve}; fi; "
        "if ! command -v uvx >/dev/null 2>&1; then "
        "echo 'magnetics-connect: installing uv (one-time, no root)…' >&2; "
        f"curl -LsSf {UV_INSTALLER} | sh || exit 1; "
        'export PATH="$HOME/.local/bin:$PATH"; fi; '
        "echo 'magnetics-connect: launching via uvx (first run provisions Python + deps)…' >&2; "
        f"exec uvx {from_opt}{PACKAGE} {serve}"
    )


def resolve_remote_cmd(template: str, port: int) -> str:
    """Substitute the chosen remote port into the serve command (every
    ``{port}`` occurrence; the bootstrap names it more than once)."""
    if "{port}" in template:
        return template.replace("{port}", str(port))
    return f"{template} --port {port}"


def build_probe_cmd(target: str, sock: str, jump: str | None, ssh_opts: list[str]) -> list[str]:
    cmd = ["ssh", *_ctl_opts(sock)]
    for opt in ssh_opts:
        cmd += ["-o", opt]
    if jump:
        cmd += ["-J", jump]
    cmd += [target, f"python3 -c {shlex.quote(_PROBE_PY)}"]
    return cmd


def build_serve_cmd(
    target: str,
    sock: str,
    local_port: int,
    remote_port: int,
    remote_cmd: str,
    jump: str | None,
    ssh_opts: list[str],
) -> list[str]:
    # -tt forces a remote pty even with our stdout piped, so when this ssh dies
    # (Ctrl-C, laptop lid) the server gets SIGHUP -- no orphans on a shared node.
    cmd = ["ssh", *_ctl_opts(sock), "-tt", "-o", "ExitOnForwardFailure=yes"]
    for opt in ssh_opts:
        cmd += ["-o", opt]
    if jump:
        cmd += ["-J", jump]
    cmd += ["-L", f"{local_port}:127.0.0.1:{remote_port}"]
    # A login shell picks up module-/profile-managed PATHs that a bare ssh
    # command shell would miss (module load in ~/.bash_profile etc.).
    cmd += [target, f"bash -lc {shlex.quote(remote_cmd)}"]
    return cmd


def pick_local_port(preferred: int | None = None) -> int:
    """`preferred` if it is free locally (same number both ends reads nicer),
    else any OS-assigned free port."""
    if preferred:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", preferred))
                return preferred
            except OSError:
                pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(url: str, child: subprocess.Popen, timeout: float) -> bool:
    """Poll `url` through the tunnel until the server answers (any HTTP status)
    or `child` (the ssh carrying it) exits / `timeout` passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except urllib.error.HTTPError:
            return True  # an HTTP response IS the server answering
        except Exception:
            time.sleep(0.5)
    return False


def _pump(stream, prefix: str, tail: collections.deque) -> None:
    """Mirror the remote server's output locally, keeping a tail for error dumps."""
    for line in stream:
        line = line.rstrip("\r\n")
        tail.append(line)
        sys.stdout.write(f"{prefix}{line}\n")
        sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="magnetics-connect",
        description="Start the magnetics GUI on a remote host and open it in your local browser.",
    )
    ap.add_argument("host", help="ssh destination: a ~/.ssh/config alias or user@host")
    ap.add_argument(
        "-J",
        "--jump",
        default=None,
        help="ProxyJump gateway (user@host[:port]); omit when the alias carries its own",
    )
    ap.add_argument(
        "--remote-cmd",
        default=None,
        help="full override for the command that starts the server on HOST, with "
        "{port} substituted; run through `bash -lc`. Bypasses the uv/uvx "
        "bootstrap — use when you have your own launch line (e.g. a module load).",
    )
    ap.add_argument(
        "--install-from",
        default=None,
        metavar="SOURCE",
        help="install the server from SOURCE instead of PyPI (a wheel URL/path or "
        "any uv source), passed to `uvx --from`. The shim until the package is "
        "on PyPI; ignored if the remote already has `magnetics` installed.",
    )
    ap.add_argument(
        "--data-dir",
        default=None,
        help="remote shot-data directory, forwarded to the launch command "
        "(on a cluster, point at scratch/project space)",
    )
    ap.add_argument(
        "--remote-port",
        type=int,
        default=None,
        help="fixed remote port (default: ask the remote for a free one)",
    )
    ap.add_argument(
        "--local-port",
        type=int,
        default=None,
        help="fixed local port (default: mirror the remote port when free)",
    )
    ap.add_argument("--no-browser", action="store_true", help="print the URL, don't open it")
    ap.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="seconds to wait for the remote server to answer (default: 300; the "
        "first uvx run provisions Python + deps and can be slow)",
    )
    ap.add_argument(
        "-o",
        "--ssh-opt",
        action="append",
        default=[],
        metavar="OPT",
        help="extra ssh -o option (repeatable), e.g. -o ConnectTimeout=30",
    )
    args = ap.parse_args(argv)

    sock = control_sock(args.host)
    remote_cmd_template = args.remote_cmd or default_remote_cmd(args.data_dir, args.install_from)

    # 1) probe: authenticates the master (prompts go to the tty, not our pipe)
    #    and reports a free remote loopback port + the actual node we landed on.
    print(f"Connecting to {args.host}" + (f" via {args.jump}" if args.jump else "") + " ...")
    probe = subprocess.run(
        build_probe_cmd(args.host, sock, args.jump, args.ssh_opt),
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        if probe.returncode != 0:
            print(
                "error: could not reach the remote host (check the ssh alias / "
                "gateway / credentials).",
                file=sys.stderr,
            )
            return 1
        probed_port, _, node = probe.stdout.strip().partition(" ")
        remote_port = args.remote_port or int(probed_port)
        local_port = args.local_port or pick_local_port(remote_port)
        url = f"http://localhost:{local_port}"

        # 2) one connection carries both the tunnel and the server process.
        remote_cmd = resolve_remote_cmd(remote_cmd_template, remote_port)
        print(f"Starting on {node or args.host}: {remote_cmd}")
        child = subprocess.Popen(
            build_serve_cmd(
                args.host, sock, local_port, remote_port, remote_cmd, args.jump, args.ssh_opt
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tail: collections.deque = collections.deque(maxlen=25)
        threading.Thread(
            target=_pump, args=(child.stdout, f"  [{args.host}] ", tail), daemon=True
        ).start()

        # 3) the server is up when it answers through the tunnel.
        if not _wait_ready(url, child, args.timeout):
            child.terminate()
            print(
                f"error: the remote server never answered on {url} within "
                f"{args.timeout:.0f}s (last output above). If it was still "
                "installing, retry with a larger --timeout; otherwise check the "
                "remote can reach PyPI, or pass --install-from / --remote-cmd.",
                file=sys.stderr,
            )
            return 1

        print()
        print(f"  magnetics GUI:  {url}")
        print(f"  server:         {node or args.host}, port {remote_port} (loopback only)")
        print("  Ctrl-C to stop both ends.")
        print()
        if not args.no_browser:
            webbrowser.open(url)

        try:
            return child.wait()
        except KeyboardInterrupt:
            child.terminate()
            child.wait(timeout=10)
            print("\nStopped.")
            return 0
    finally:
        subprocess.run(
            ["ssh", "-o", f"ControlPath={sock}", "-O", "exit", args.host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    raise SystemExit(main())
