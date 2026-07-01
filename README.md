# magnetics (analysis)

Device-agnostic Python library for 3D magnetic-sensor analysis of tokamak MHD
instabilities. See `../docs/VISION.md` for context.

## Setup

```sh
uv sync --group dev
uv run nbstripout --install   # strip notebook outputs on commit (run once per clone)
```

## Layout

- `src/magnetics/core/` — pure, device-agnostic analysis (e.g. `spectral.py`).
- `tests/` — pytest suite; fixtures in `tests/fixtures/`.
- `examples/` — runnable Jupyter notebooks.

## Common commands

```sh
uv run pytest                                   # run tests
uv run jupyter lab examples/                    # open the example notebooks
```
