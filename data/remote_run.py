#!/usr/bin/env python3
"""
Run a toksearch pull ON the GA cluster, from your laptop, with zero manual copying.

A new user should not have to rsync the fetcher to the cluster by hand. This module
does the whole round trip over a single authenticated SSH connection:

  1. open one SSH master to the cluster (reused below);
  2. rsync the fetcher (toksearch_fetch.py + magnetics_signals.py + inspect_h5.py)
     to the cluster automatically;
  3. run `toksearch_fetch.py --backend toksearch ...` there, where PTDATA is local
     and toksearch lives (loaded via the configured `setup` command);
  4. rsync the resulting .h5 back into the local data/datafile/ dir.

Auth: if `password` is given (e.g. from the GUI), it is fed to ssh via an
SSH_ASKPASS helper so NO terminal prompt is needed — the password answers the
password prompt and `duo` answers the Duo prompt (default "1" = Duo Push, which
also works across the jump hop where a one-time passcode would not). If no
password is given, ssh prompts interactively in the terminal as usual.

Defaults target omega via the cybele gateway with the conda toksearch env; all of
it is configurable. Secrets are passed once to the local ssh subprocess and never
stored.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from sshauth import askpass_env

HERE = Path(__file__).resolve().parent          # repo data/ dir (the fetcher lives here)
LOCAL_OUT = HERE / "datafile"                    # where pulled .h5 land locally
SYNC_FILES = ["toksearch_fetch.py", "magnetics_signals.py", "inspect_h5.py",
              "sshauth.py"]

# Cluster defaults (override via args / CLI flags). The setup command is run in a
# login shell before the fetch so `module`/`conda` are available.
DEFAULT_HOST = "omega"
DEFAULT_JUMP = "cybele.gat.com"
DEFAULT_DIR = "~/magnetics_fetch"
# `conda activate` needs conda's shell function, which a non-interactive `bash -lc`
# does not get for free — source conda.sh first, or activation silently no-ops and
# `python` stays the system one (→ "toksearch not installed").
DEFAULT_SETUP = (
    'module purge && module load conda && '
    'source "$(conda info --base)/etc/profile.d/conda.sh" && '
    'conda activate toksearch_env'
)

def _log(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def run_remote(shot, analysis="both", *, host=DEFAULT_HOST, jump=DEFAULT_JUMP,
               username=None, password=None, duo=None, remote_dir=DEFAULT_DIR,
               setup=DEFAULT_SETUP, tmin=None, tmax=None, decimate=1,
               local_out_dir=None, progress=None) -> str:
    """Sync code → run the pull on the cluster → copy the .h5 back. Returns the
    local path of the fetched file."""
    if not username:
        username = input("GA username: ").strip()
    if not username:
        sys.exit("A username is required for the remote backend.")

    env, cleanup = (askpass_env(password, duo) if password else (None, lambda: None))

    target = f"{username}@{host}"
    sock = f"/tmp/ms-{username}-{host}.sock"  # short ControlPath (macOS length limit)
    ctl = ["-o", "ControlMaster=auto", "-o", f"ControlPath={sock}",
           "-o", "ControlPersist=300"]
    reuse = ["ssh", "-o", f"ControlPath={sock}"]  # subsequent hops reuse the master

    def run(cmd, **kw):
        return subprocess.run(cmd, env=env, **kw)

    try:
        # 1) establish ONE authenticated master connection.
        master = ["ssh", *ctl, "-o", "ExitOnForwardFailure=yes"]
        if jump:
            master += ["-J", f"{username}@{jump}"]
        master += [target, "true"]
        _log(f"Connecting to {target}" + (f" via {jump}" if jump else "")
             + (" (using GUI-supplied credentials; approve Duo if pushed)"
                if password else " (password + Duo prompt) ..."))
        if run(master).returncode != 0:
            sys.exit("SSH to the cluster failed (check username/password/Duo).")

        # 2) ensure the remote dir exists, then rsync the fetcher up.
        out_remote = f"{remote_dir}/out"
        run([*reuse, target, f"mkdir -p {remote_dir} {out_remote}"], check=True)
        _log(f"Syncing fetcher → {target}:{remote_dir}/ ...")
        rsh = f"ssh -o ControlPath={sock}"  # rsync reuses the master connection
        run(["rsync", "-az", "-e", rsh, *[str(HERE / f) for f in SYNC_FILES],
             f"{target}:{remote_dir}/"], check=True)

        # 3) run the pull on the cluster (login shell so module/conda work).
        remote_out = f"out/shot_{shot}.h5"
        fetch = ["python", "toksearch_fetch.py", "--backend", "toksearch",
                 "--shot", str(shot), "--analysis", analysis, "--out", remote_out]
        if tmin is not None:
            fetch += ["--tmin", str(tmin)]
        if tmax is not None:
            fetch += ["--tmax", str(tmax)]
        if decimate and decimate > 1:
            fetch += ["--decimate", str(decimate)]
        inner = f"cd {remote_dir} && {setup} && {shlex.join(fetch)}"
        _log(f"Running on {host}: {shlex.join(fetch)}")
        if progress:
            progress(0.5, f"pulling shot {shot} on {host}")
        if run([*reuse, target, f"bash -lc {shlex.quote(inner)}"]).returncode != 0:
            sys.exit("remote fetch failed.")

        # 4) copy the result back.
        out_dir = Path(local_out_dir) if local_out_dir else LOCAL_OUT
        out_dir.mkdir(parents=True, exist_ok=True)
        local_path = out_dir / f"shot_{shot}.h5"
        _log(f"Copying result → {local_path} ...")
        run(["rsync", "-az", "-e", rsh,
             f"{target}:{remote_dir}/{remote_out}", str(local_path)], check=True)
        if progress:
            progress(1.0, f"done: {local_path.name}")
        _log(f"Saved {local_path}")
        return str(local_path)
    finally:
        run([*reuse, "-O", "exit", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cleanup()
