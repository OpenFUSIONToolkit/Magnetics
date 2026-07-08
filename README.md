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

Two more console scripts come with the install:

```sh
magnetics-fetch --shot 184927 # pull a shot to the local data dir
magnetics-service             # start just the API/service (honors HOST/PORT)
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
