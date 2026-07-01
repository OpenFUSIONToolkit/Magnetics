#!/usr/bin/env python3
"""
Run a toksearch pull ON the GA cluster, from your laptop, with zero manual copying.

A new user should not have to rsync the fetcher to the cluster by hand. This module
does the whole round trip over a single authenticated SSH connection:

  1. open one SSH master to the cluster (reused below);
  2. rsync the fetcher (toksearch_fetch.py + magnetics_signals.py) up;
  3. run the fetcher there with the cluster env's interpreter directly -- PTDATA is
     local and `toksearch_d3d` reads it natively (benchmarked ~5-7x faster than
     mdsip), then writes a compact (lzf) .h5;
  4. rsync that .h5 back into the local data/datafile/ dir.

Why this beats the laptop mdsthin pull: only the *compressed* .h5 crosses the tunnel
(~80 MB) instead of ~370 MB of raw float over mdsip. Measured end-to-end ~21-24s
cold (vs ~60s laptop) -- after which all fitting is local and instant.

Connection: the cluster login is EXPLICIT and device-resolved -- the real host,
port, and env interpreter come from the device file's `network.cluster` block
(DIII-D: omega.gat.com), so a fresh laptop needs no ~/.ssh/config Host alias, only
a GA `username` + key (or password/Duo). The gateway hop is chosen automatically:
off-site we ProxyJump through `network.jump` (cybele.gat.com:2039); on-site (an
FQDN under `network.domain`) we go straight in with no jump. To use a personal
ssh-config alias that bakes in its own ProxyJump, pass `host=<alias>` AND an empty
`jump=""` so the alias's ProxyJump is used without a double-jump.

Environment: we do NOT `module load` or `conda activate` on the cluster. The env's
activate.d scripts set nothing the fetch needs, so we invoke the env interpreter
directly (`python` arg) -- simpler, and ~4-5s faster per pull than `conda run`.

Auth: if `password` is given (e.g. from the GUI), it is fed to ssh via an
SSH_ASKPASS helper so no terminal prompt is needed (`duo` answers the Duo prompt,
default "1" = Duo Push). With a key-based ssh-config alias (the default), no
password is needed at all. Secrets are passed once to ssh and never stored.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from .. import h5source
from .network import cluster_login, gateway_address, on_site_network
from ..sshauth import askpass_env

# The importable package root (…/src/magnetics). We rsync it to the cluster so the
# fetcher runs there as `python -m magnetics.data.fetch.toksearch` (relative imports
# intact) instead of as a loose script — one code path for laptop and cluster.
PKG_ROOT = Path(__file__).resolve().parents[2]  # …/src/magnetics
PKG_NAME = PKG_ROOT.name  # "magnetics"
LOCAL_OUT = h5source.data_dir() / "datafile"  # where pulled .h5 land locally

# Cluster connection: resolved from the device file's `network.cluster` block (the
# source of truth, so this is device-agnostic); these module-level values are the
# fallback when the device omits a field. Explicit args / CLI flags override both.
DEFAULT_HOST = "omega.gat.com"  # real cluster host (no ~/.ssh/config alias needed)
DEFAULT_JUMP = "cybele.gat.com:2039"  # gateway ProxyJump to reach the cluster
DEFAULT_DIR = "~/magnetics_fetch"
# Invoke the cluster env's interpreter DIRECTLY -- no `module load` / `conda activate`
# (its activate.d scripts set nothing PTDATA needs; direct is ~4-5s faster per pull).
DEFAULT_PYTHON = "/fusion/projects/codes/conda/omega/envs_public/toksearch_env/bin/python"


def _log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def run_remote(
    shot,
    analysis="both",
    *,
    host=None,
    jump=None,
    username=None,
    password=None,
    duo=None,
    remote_dir=DEFAULT_DIR,
    python=None,
    tmin=None,
    tmax=None,
    decimate=1,
    device="diiid",
    sensor_set=None,
    local_out_dir=None,
    progress=None,
) -> str:
    """Sync code → run the pull on the cluster → copy the .h5 back. Returns the
    local path of the fetched file.

    `host`/`python` default to the device file's `network.cluster` block (then the
    module fallbacks) when not passed, so the cluster address is explicit in config
    rather than a user's ~/.ssh/config alias. `jump` (None → auto) is the site
    gateway from `network.jump` off-site and dropped when on-site (already inside
    the network, no hop needed); pass an explicit host[:port] to force one, or an
    empty string to force none (e.g. an ssh-config alias that carries its own
    ProxyJump)."""
    login = cluster_login(device)
    host = host or login["host"] or DEFAULT_HOST
    port = login["port"]  # cluster SSH port (22 unless the device overrides it)
    python = python or login["python"] or DEFAULT_PYTHON
    if jump is None:  # not explicitly set → auto: gateway off-site, none on-site
        jump = None if on_site_network(device) else (gateway_address(device) or DEFAULT_JUMP)

    env, cleanup = askpass_env(password, duo) if password else (None, lambda: None)

    # host/jump may be ~/.ssh/config aliases (User/port/key/ProxyJump from config) or
    # raw hosts; only prepend user@ when an explicit username overrides the alias.
    target = f"{username}@{host}" if username else host
    tag = (f"{username}-" if username else "") + host.replace("/", "_")
    sock = f"/tmp/ms-{tag}.sock"  # short ControlPath (macOS length limit)
    # A non-standard cluster SSH port only needs to be set on the master connect;
    # reuse/rsync attach to the same ControlPath socket regardless of port.
    port_opt = ["-p", str(port)] if port and port != 22 else []
    ctl = ["-o", "ControlMaster=auto", "-o", f"ControlPath={sock}", "-o", "ControlPersist=300"]
    reuse = ["ssh", "-o", f"ControlPath={sock}"]  # subsequent hops reuse the master

    def run(cmd, **kw):
        return subprocess.run(cmd, env=env, **kw)

    try:
        # 1) establish ONE authenticated master connection (alias supplies the jump).
        master = ["ssh", *ctl, *port_opt]
        if jump:
            master += ["-J", f"{username}@{jump}" if username else jump]
        master += [target, "true"]
        _log(
            f"Connecting to {target}"
            + (f" via {jump}" if jump else "")
            + (" (using supplied credentials; approve Duo if pushed)" if password else " ...")
        )
        if run(master).returncode != 0:
            sys.exit(
                "SSH to the cluster failed (check the ssh-config alias / "
                "username / password / Duo)."
            )

        # 2) ensure the remote dir exists, then rsync the fetcher up.
        out_remote = f"{remote_dir}/out"
        run([*reuse, target, f"mkdir -p {remote_dir} {out_remote}"], check=True)
        _log(f"Syncing {PKG_NAME} package → {target}:{remote_dir}/ ...")
        rsh = f"ssh -o ControlPath={sock}"  # rsync reuses the master connection
        run(
            [
                "rsync",
                "-az",
                "-e",
                rsh,
                "--exclude",
                "__pycache__",
                str(PKG_ROOT),
                f"{target}:{remote_dir}/",
            ],
            check=True,
        )

        # 3) run the pull on the cluster via the env interpreter directly.
        remote_out = f"out/shot_{shot}.h5"
        fetch = [
            python,
            "-m",
            "magnetics.data.fetch.toksearch",
            "--backend",
            "toksearch",
            "--shot",
            str(shot),
            "--device",
            device,
            "--out",
            remote_out,
        ]
        if sensor_set:
            fetch += ["--sensor-set", sensor_set]
        else:
            fetch += ["--analysis", analysis]
        if tmin is not None:
            fetch += ["--tmin", str(tmin)]
        if tmax is not None:
            fetch += ["--tmax", str(tmax)]
        if decimate and decimate > 1:
            fetch += ["--decimate", str(decimate)]
        # TOKSEARCH_INDEX_DIR only matters for SQL/index shot *discovery*; we pass an
        # explicit shotlist, so point it at the workdir to silence ~1 warning/signal.
        inner = (
            f'cd {remote_dir} && PYTHONPATH="$PWD" TOKSEARCH_INDEX_DIR="$PWD" {shlex.join(fetch)}'
        )
        _log(f"Running on {host}: {shlex.join(fetch)}")
        if progress:
            progress(0.5, f"pulling shot {shot} on {host}")
        if run([*reuse, target, inner]).returncode != 0:
            sys.exit("remote fetch failed.")

        # 4) copy the result back.
        out_dir = Path(local_out_dir) if local_out_dir else LOCAL_OUT
        out_dir.mkdir(parents=True, exist_ok=True)
        local_path = out_dir / f"shot_{shot}.h5"
        _log(f"Copying result → {local_path} ...")
        run(
            ["rsync", "-az", "-e", rsh, f"{target}:{remote_dir}/{remote_out}", str(local_path)],
            check=True,
        )
        if progress:
            progress(1.0, f"done: {local_path.name}")
        _log(f"Saved {local_path}")
        return str(local_path)
    finally:
        run([*reuse, "-O", "exit", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cleanup()
