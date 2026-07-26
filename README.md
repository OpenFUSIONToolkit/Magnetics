# magnetics

Device-agnostic Python library **and** GUI for 3D magnetic-sensor analysis of
tokamak MHD instabilities — quasi-stationary (locked) modes and rapidly-rotating
modes. See [`docs/VISION.md`](docs/VISION.md) for context.

## Quick start (no dev setup)

The GUI ships inside the package — no Node or build toolchain needed.

```sh
uvx magnetics                 # zero-install: uv provisions Python + runs it
# or
pip install magnetics         # into an existing environment
magnetics                     # start the app, open it in your browser
```

`magnetics` starts the service and opens the GUI in your browser. Useful flags:

```sh
magnetics --port 8000         # fixed port (default: first free port from 8000)
magnetics --no-browser        # headless (e.g. on a server)
magnetics --data-dir PATH     # where shot data lives (see below)
```

Three more console scripts come with the install:

```sh
magnetics-fetch --shot 184927 # pull a shot to the local data dir
magnetics-service             # start just the API/service (honors HOST/PORT)
magnetics-connect omega       # run the server on a remote host, browse it locally
```

### Where shot data lives

Fetched shots are cached persistently so you don't re-pull them. The location is,
in order:

1. `$MAGNETICS_DATA_DIR` (or `--data-dir`) if set — **the** knob to relocate it;
2. the repo's `data/` dir when run from a source checkout;
3. otherwise a per-user data dir (`~/.local/share/magnetics` on Linux,
   `~/Library/Application Support/magnetics` on macOS).

**On a cluster,** set `MAGNETICS_DATA_DIR` to scratch/project space (home dirs are
usually quota'd and shot files are large) — e.g. in your shell profile:

```sh
export MAGNETICS_DATA_DIR=$SCRATCH/magnetics
```

## Remote use — run on a cluster, browse locally

The server should run where the data lives (a cluster work node), but that is
rarely where your browser lives — you're on a laptop off-site, or on a NoMachine
desktop on the site's login/gateway node with a firewall between you and the
work node. `magnetics-connect` does the standard SSH-tunnel dance in one command:
it opens one authenticated connection to the host, asks it for a free port and
its real node name, starts the server there **bound to loopback only**, carries
a `-L` port-forward on the same connection, and opens your local browser once
the server answers through the tunnel. Only HTTP crosses the wire — fetches and
fits run next to the data, plots stream back. Ctrl-C stops both ends.

```sh
magnetics-connect omega                        # ~/.ssh/config alias (keys, ProxyJump)
magnetics-connect me@omega.gat.com -J me@cybele.gat.com:2039
magnetics-connect omega --data-dir /cscratch/$USER/magnetics
magnetics-connect flux --remote-cmd \
    'module load magnetics && magnetics --no-browser --port {port}'
```

**Zero-install on the remote.** By default the launcher bootstraps the server
for you: it runs an already-installed `magnetics` if the host has one; otherwise
it installs `uv` (the official root-free installer, into `~/.local/bin`) and
launches with `uvx magnetics`, which fetches the package **and provisions its own
Python** — so a bare cluster node with only an old system Python needs nothing
installed by hand. The first run downloads + provisions (slower; watch the
streamed `[host]` log); later runs are cached and fast.

- `--install-from SOURCE` — install from a wheel URL/path (any uv source) instead
  of PyPI. This is the shim until `magnetics` is published to PyPI.
- `--remote-cmd '…{port}…'` — full override of the launch line (bypasses the
  bootstrap), e.g. for an eventual `module load magnetics`.

The launcher itself is **stdlib-only and standalone** — on a gateway node with
only system `python3`, copy the single file and run it directly:

```sh
scp src/magnetics/connect.py gateway:
python3 connect.py omega
```

## Development

The Python project is the repo root (a uv project); the React GUI is in `gui/web/`.

```sh
uv sync --group dev
uv run nbstripout --install   # strip notebook outputs on commit (run once per clone)
./run-dev.sh                  # live: FastAPI service + GUI dev server (hot reload)
./run-dev.sh static           # GUI only, static mock fixtures (offline frontend work)
./run-dev.sh --prod           # build the GUI and serve it on one port (preview the wheel)

scripts/build-dist.sh         # build the distributable wheel + sdist (GUI bundled) into dist/
scripts/build-dist.sh --smoke # …and smoke-test the wheel in a clean venv
```

### Running a built wheel in isolation

To try a freshly built wheel the way an end user would — in a throwaway
environment that touches neither your `.venv` nor the repo's `data/` — run it with
`uvx --from` (the installed package lives in uv's cache, so it uses the per-user
data dir, not this checkout):

```sh
uvx --from ./dist/magnetics-*.whl magnetics
uvx --from ./dist/magnetics-*.whl magnetics --data-dir "$(mktemp -d)"  # touch nothing persistent
uvx --reinstall --from ./dist/magnetics-*.whl magnetics                # after a rebuild at the same version
```

### Layout

- `src/magnetics/core/` — pure, device-agnostic analysis (e.g. `spectral.py`).
- `src/magnetics/service/` — FastAPI app; the built GUI is bundled at `service/webapp/`.
- `gui/web/` — React + Vite + TypeScript frontend.
- `tests/` — pytest suite (synthetic fixtures; no real tokamak data committed).
- `examples/` — runnable Jupyter notebooks.

### Common commands

```sh
uv run pytest                                   # run the Python tests
uv run jupyter lab examples/                    # open the example notebooks
cd gui/web && npm test                          # run the frontend tests
```

Releasing to PyPI is documented in [`docs/RELEASING.md`](docs/RELEASING.md).
