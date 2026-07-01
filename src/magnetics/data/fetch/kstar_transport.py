#!/usr/bin/env python3
"""KSTAR transport: bring up the KFE Cisco VPN, then an SSH tunnel to the MDS
server, and yield the local mdsip port for mdsthin to connect to.

Ported from the team's KSTAR tooling (EF/KSTAR/helpers.py + the KDT config). KSTAR's
MDS host (mdsr.kstar.kfe.re.kr) sits behind the KFE VPN and is reached as::

    AnyConnect(vpn.kfe.re.kr)
      -> ssh -p 2201 nkstar.kstar.kfe.re.kr -L 8005:mdsr.kstar.kfe.re.kr:8005
        -> mdsthin Connection("<ssh_user>@localhost:8005")

Two usernames are involved: the VPN account is ``k-<id>`` while the SSH/MDS account
is ``<id>`` (the VPN adds a ``k-`` prefix to the same id). Credentials are ALWAYS
passed in by the caller (GUI/CLI) or prompted interactively -- nothing is stored here.

Needs the Cisco VPN CLI and ``pexpect``; it cannot run offline, so it is imported
lazily only when a KSTAR pull is actually requested. Endpoints default to the values
in ``kstar.json``'s ``connection`` block but can be overridden via ``conn``.
"""

from __future__ import annotations

import contextlib
import os
import socket
import subprocess
import sys
import time

# Defaults mirror kstar.json's "connection" block; callers normally pass `conn`.
DEFAULTS = {
    "vpn_url": "https://vpn.kfe.re.kr",
    "vpn_executable_candidates": [
        "/opt/cisco/secureclient/bin/vpn",  # Cisco Secure Client (current)
        "/opt/cisco/anyconnect/bin/vpn",  # legacy AnyConnect
    ],
    "ssh_host": "nkstar.kstar.kfe.re.kr",
    "ssh_port": 2201,
    "mds_host": "mdsr.kstar.kfe.re.kr",
    "mds_port": 8005,
    "local_port": 8005,
}


def _find_vpn_cli(candidates) -> str:
    """The Cisco VPN CLI path, or exit with an actionable message. $KSTAR_VPN_CLI
    overrides for a non-standard install."""
    override = os.environ.get("KSTAR_VPN_CLI")
    for path in [override, *candidates] if override else candidates:
        if path and os.path.exists(path):
            return path
    sys.exit(
        "Cisco VPN CLI not found (looked in "
        f"{', '.join(candidates)}). Install Cisco Secure Client / AnyConnect "
        "or set $KSTAR_VPN_CLI to the `vpn` binary."
    )


def _twofa(duo) -> str:
    """Resolve the 2FA response. An explicit ``duo`` ('push' or a passcode) is sent
    as-is; otherwise (None/'ask') prompt for a fresh passcode at connect time (KFE
    accounts use a one-time 2FA passcode, not push)."""
    if duo and str(duo).lower() != "ask":
        return str(duo).strip()
    import getpass

    return getpass.getpass("KFE 2FA passcode (or 'push'): ").strip()


def _wait_tcp(host, port, timeout=12) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            socket.create_connection((host, port), 0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def _force_disconnect(cli, debug=False) -> bool:
    """Guarantee the VPN is down, independent of the pexpect child. An interactive
    `disconnect` can be lost if the child is closed before AnyConnect acts on it; a
    separate `vpn disconnect` is idempotent and does not depend on that child. Poll
    `vpn state` and return True only once nothing reports `state: Connected`."""
    out = None if debug else subprocess.DEVNULL
    with contextlib.suppress(Exception):
        subprocess.run([cli, "disconnect"], stdout=out, stderr=out, timeout=30)
    for _ in range(20):  # ~6s for the tunnel to fully drop
        try:
            state = subprocess.run(
                [cli, "state"], capture_output=True, text=True, timeout=10
            ).stdout
        except Exception:
            return False
        if "state: Connected" not in state:
            return True
        time.sleep(0.3)
    return False


@contextlib.contextmanager
def _vpn(cli, url, username, password, ssh_host, ssh_port, *, duo="push", debug=False):
    import pexpect  # lazy: only needed for a live KSTAR pull

    # ssh_host/ssh_port are the KSTAR tunnel endpoint, used for the reachability check.
    # The GUI app holds the "connect capability"; the CLI can't connect while it runs.
    # Its process name differs across versions (Secure Client vs legacy AnyConnect).
    for _proc in ("Cisco Secure Client", "vpnui", "Cisco AnyConnect Secure Mobility Client"):
        subprocess.run(["killall", _proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child = pexpect.spawn(cli, [], encoding="utf-8", timeout=90)
    if debug:
        child.logfile = sys.stderr
    child.expect(r"VPN>\s*$")
    child.sendline(f"connect {url}")
    started = False
    pw_sent = False  # AnyConnect shows two "Password" prompts: primary, then 2FA
    while True:
        i = child.expect(
            [
                r"Group:.*",
                r"Username:.*",
                r"Password:.*",
                r"(Second Password|Passcode|Enter a passcode|Duo two-factor|Answer).*",
                r"Accept\?\s*\[y/n\].*",
                r"state:\s*Connected",
                r"Authentication failed",
                r"(Another (AnyConnect|Cisco Secure Client)|Connect capability is unavailable)",
                r"state:\s*Disconnected",
                r"(?i)contacting .*",
                pexpect.TIMEOUT,
                pexpect.EOF,
            ]
        )
        if i == 0:
            started = True
            child.sendline("")
        elif i == 1:
            started = True
            child.sendline(username)
        elif i == 2:
            # First "Password:" is the primary; a later one is the 2FA passcode.
            started = True
            if not pw_sent:
                child.sendline(password)
                pw_sent = True
            else:
                child.sendline(_twofa(duo))
        elif i == 3:
            started = True
            child.sendline(_twofa(duo))
        elif i == 4:
            child.sendline("y")
        elif i == 5:
            break
        elif i == 6:
            raise RuntimeError("KFE VPN: authentication failed (user/pass/2FA).")
        elif i == 7:
            raise RuntimeError(
                "The Cisco Secure Client GUI app owns the VPN connect capability. "
                'Quit it (menu-bar icon -> Quit, or `killall "Cisco Secure Client"`) '
                "and retry."
            )
        elif i == 8:
            if started:
                raise RuntimeError("KFE VPN: disconnected during login.")
        elif i in (10, 11):
            if _wait_tcp(ssh_host, ssh_port, 12):
                break
            raise RuntimeError("KFE VPN: login timed out before connecting.")
    if not _wait_tcp(ssh_host, ssh_port, 12):
        raise RuntimeError(f"VPN up but {ssh_host}:{ssh_port} unreachable (group/ACL).")
    try:
        yield
    finally:
        # Kill the tunnel robustly: ask the child to disconnect and wait for it to
        # report Disconnected, then fire an independent idempotent `vpn disconnect`
        # backstop and confirm. Honors the "kill VPN when done pulling" rule.
        with contextlib.suppress(Exception):
            child.sendline("disconnect")
            child.expect([r"state:\s*Disconnected", pexpect.EOF, pexpect.TIMEOUT], timeout=15)
            child.sendline("quit")
            child.close(force=True)
        if not _force_disconnect(cli, debug=debug):
            sys.stderr.write(
                f"WARNING: KFE VPN may still be connected — run `{cli} disconnect` to be sure.\n"
            )


@contextlib.contextmanager
def _tunnel(
    ssh_user,
    ssh_host,
    ssh_port,
    mds_host,
    mds_port,
    local_port,
    ssh_password=None,
    *,
    duo="push",
    debug=False,
):
    import pexpect
    import getpass

    cmd = (
        f"ssh -p {ssh_port} -o ExitOnForwardFailure=yes "
        f"-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N "
        f"-L {local_port}:{mds_host}:{mds_port} {ssh_user}@{ssh_host}"
    )
    child = pexpect.spawn("/bin/sh", ["-lc", cmd], encoding="utf-8", timeout=120)
    if debug:
        child.logfile = sys.stderr
    pw_sent = False  # nkstar may prompt password THEN a one-time code (2nd prompt)
    polls = 0  # bound the post-auth silent-wait so we can't loop forever
    while True:
        # `ssh -N` is SILENT after auth, so poll on a short timeout: once the local
        # forward is listening we're done, rather than waiting on pexpect's default.
        i = child.expect(
            [
                r"Are you sure you want to continue connecting.*\?",
                r"(?i)password:\s*$",
                r"(?i)(duo|two[- ]?factor|2fa|passcode|verification code|otp|response|oath).*:",
                r"Permission denied",
                r"bind: Address already in use",
                pexpect.TIMEOUT,
                pexpect.EOF,
            ],
            timeout=5,
        )
        if i == 0:
            child.sendline("yes")
        elif i == 1:
            if not pw_sent:
                child.sendline(
                    ssh_password or getpass.getpass(f"SSH password for {ssh_user}@{ssh_host}: ")
                )
                pw_sent = True
                sys.stderr.write("  authenticated; opening KSTAR tunnel...\n")
            else:
                child.sendline(_twofa(duo))  # a 2nd Password: prompt is the OTP
        elif i == 2:
            child.sendline(_twofa(duo))
        elif i == 3:
            raise RuntimeError("KSTAR SSH authentication failed (password/2FA).")
        elif i == 4:
            break  # already forwarded elsewhere; proceed
        else:  # TIMEOUT or EOF
            if _wait_tcp("127.0.0.1", local_port, 1):
                break  # forward is up -> success (ssh -N went silent)
            if i == 6:  # EOF: ssh exited without establishing the forward
                raise RuntimeError("KSTAR SSH exited before the tunnel came up (auth rejected?).")
            if not pw_sent:
                continue  # still waiting for the first prompt over the VPN
            polls += 1
            if polls > 8:  # ~40s of silence after auth with no listener
                break  # fall through to the final _wait_tcp check / error
            continue  # authenticated; keep polling for the listener
    if not _wait_tcp("127.0.0.1", local_port, 15):
        with contextlib.suppress(Exception):
            child.close(force=True)
        raise RuntimeError(f"KSTAR tunnel failed to come up (localhost:{local_port}).")
    try:
        yield local_port
    finally:
        with contextlib.suppress(Exception):
            child.close(force=True)


@contextlib.contextmanager
def session(
    *,
    vpn_username=None,
    vpn_password=None,
    ssh_username=None,
    ssh_password=None,
    duo=None,
    conn=None,
    debug=False,
):
    """VPN + SSH tunnel up; yields the local mdsip port. Credentials are passed in
    (GUI) or prompted (CLI). SSH creds default to the VPN account id: if only a VPN
    username ``k-<id>`` is given, the SSH user is ``<id>``. ``conn`` is kstar.json's
    ``connection`` block (endpoints); falls back to DEFAULTS."""
    c = {**DEFAULTS, **(conn or {})}
    if not vpn_username:
        vpn_username = input("KFE VPN username (e.g. k-<id>): ").strip()
    if not vpn_username:
        sys.exit("A VPN username is required for the KSTAR backend.")
    if not vpn_password:
        import getpass

        vpn_password = getpass.getpass("KFE VPN password: ")
    # SSH/MDS user is the VPN id without the 'k-' prefix, unless given explicitly.
    if not ssh_username:
        ssh_username = vpn_username[2:] if vpn_username.startswith("k-") else vpn_username

    cli = _find_vpn_cli(c["vpn_executable_candidates"])
    with _vpn(
        cli,
        c["vpn_url"],
        vpn_username,
        vpn_password,
        c["ssh_host"],
        c["ssh_port"],
        duo=duo,
        debug=debug,
    ):
        with _tunnel(
            ssh_username,
            c["ssh_host"],
            c["ssh_port"],
            c["mds_host"],
            c["mds_port"],
            c["local_port"],
            ssh_password=ssh_password,
            duo=duo,
            debug=debug,
        ) as lport:
            yield ssh_username, lport
