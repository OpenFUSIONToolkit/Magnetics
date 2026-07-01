# magnetics-code — local OMFIT magnetics translation (3D spatial fits)

A standalone, OMFIT-free translation of the OMFIT magnetics **3D spatial-fit** workflow — the
SLCONTOUR-style quasi-stationary modal decomposition of locked / slowly-rotating MHD modes
(VISION.md §4.1). It runs locally (no OMFIT, no MDSplus) against the project-canonical data:
per-shot signals in `data/datafile/shot_<shot>.h5` and device geometry in `data/device/<device>.json`.

It fits the spatial field pattern at each time slice with a cylindrical-Fourier basis

```
δB(φ, θ) = Σ_nm  b_nm · exp(i(nφ − mθ))
```

by SVD-conditioned least squares, and reports the condition number **K** (the central trust
metric — warn K > 10, error K > 20), per-coefficient error bars, and reduced χ².

> Scope: the spatial fit of sensor **arrays**. The spectrogram / MODESPEC rotating-mode path and
> the 3D coil-current fits are intentionally out of scope here.

## Pipeline ↔ OMFIT mapping

| local module | role | OMFIT magnetics module script |
|---|---|---|
| `io_data.py` | `load_shot` reads `shot_<n>.h5` signals + the device JSON geometry (the "fetch" + "init" steps) | `fetch_magnetics.py` / `init_magnetics.py` |
| `prep.py` | trim, DC-comp, integrate, causal filter, detrend, SVD-condition | `prep_magnetics.py` |
| `fit.py` | basis matrix + SVD least-squares modal fit | `fit_magnetics.py` |
| `run.py` | `run_steps` orchestrator (load → prep → fit) | `run_magnetics.py` |
| `plots.py` | sensor map, signals, fit quality, mode amp/phase, φ-vs-time contour, SVD diagnostics | `plot_magnetics_*.py` |
| `omfit_compat.py` | OMFIT-runtime shim (`printi`, `cornernote`, `uband`, `is_device`) + the device layer (geometry, named subsets, wall — all from the device JSON) | (OMFIT framework) |

This package runs without OMFIT or MDSplus; it reads only the project-canonical data files (below).

## Data

### Per-shot signals — `data/datafile/shot_<shot>.h5`

One HDF5 file per shot (the PTDATA fetch output): a group per channel with `data` + `time`
(hard-linked into a shared `_timebases` group), **all time in milliseconds**. Channels sample at
several rates (integrated probes ~50 kHz, bdots ~200 kHz, coils/`ip`/`bt` ~20 kHz). Root attrs
include `device`, `shot`, `tmin`/`tmax` (ms), `channels_fetched`/`channels_missing`.

`io_data.load_shot` turns this into the Datasets the pipeline expects:

- `raw` — `signal(channel, time)` (time in **seconds**), `signal_sigma` (a constant 2e-5 T), and the
  per-channel geometry joined from the device JSON, including the derived `*_end1/2` coordinates.
  All sensor channels are linearly interpolated onto a single common time axis (the densest native
  grid, clipped to the window they share).
- `plasma` — `Ip`, `Bt` from the `ip`/`bt` channels (time in **ms**), `helicity` attr (default −1).
- `coupling` — `None`; the new files carry no DC vacuum-coupling matrix, so `prep`'s DC compensation
  (`dc_comp=True`) is unavailable.

### Device geometry — `data/device/<device>.json`

The canonical device description (`diiid.json` for DIII-D): `R0`, the `wall` outline, the per-sensor
base geometry (`r, z, phi, tilt, length, delta_phi, na, pair`), and named `sensor_sets`. Loaded via
`omfit_compat` (`load_device`, `sensor_geometry`, `load_wall`, `resolve_channel_filter`).
`sensor_geometry` derives `theta` and the `*_end1/2` sensor-end coordinates from the base geometry
(the OMFIT `init_magnetics.py` step).

## Quick start

```python
import sys; sys.path.insert(0, '.')        # the modules are a flat set, not a package
from run import run_steps
import plots

# load → prep → fit the LFS-midplane toroidal Bp array for n = 1,2,3
r = run_steps(199749, channel_filter='Bp_LFS_midplane', ns=(1, 2, 3), ms=(0,),
              time_trim=(3.3, 3.5), prep_kwargs=dict(cutoff_hz=(5, 250), energy=0.98))

print('condition number K =', r.condition_number)
plots.plot_fit_modes(r.fit)                 # amplitude & phase of each mode vs time
plots.plot_slice(r.fit, fix_coord='theta')  # the SLCONTOUR φ-vs-time contour
```

`channel_filter` accepts a regex, a list of regexes, or a friendly subset name — with or without
underscores (e.g. `'Bp_LFS_midplane'` or `'Bp LFS midplane'`, `'Bp_All'`, `'All_3D_Coils'`). List
them all with `io_data.available_subsets('DIII-D')`. `time_trim` must fall inside the shot file's
window (shot 199749 spans **3.3–3.5 s**).

## Device file — `data/device/diiid.json`

All device metadata lives in this single JSON (replacing the old bundled `DATA/DIII-D/*.txt` tables):

| key | content | loader (`omfit_compat`) |
|---|---|---|
| `sensor_sets` | named sensor subsets (`Bp LFS midplane`, `Bp All`, `All 3D Coils`, …) | `list_sensor_subsets`, `resolve_channel_filter` |
| `sensors` | per-sensor base geometry (`r, z, phi, tilt, length, …`) → derived ends | `sensor_geometry` (alias `load_sensor_table`) |
| `R0`, `wall` | machine major radius + first-wall outline | `load_wall` |

## The worked example

[`example_magnetics.ipynb`](example_magnetics.ipynb) walks the full pipeline end to end (sensor map,
conditioned signals, SVD diagnostics, fit quality, mode amplitude & phase, and the φ-vs-time
contour). It is **shot-agnostic**: a single *Parameters* cell at the top sets `SHOT`,
`CHANNEL_FILTER`, `TIME_TRIM`, and the mode lists — change those to analyse a different shot or
array. It defaults to shot **199749** (`Bp_LFS_midplane`, `time_trim=(3.3, 3.5)`).

Run it on the uv environment (Python 3.14), e.g. a quick headless smoke test of the same pipeline:

```bash
cd analysis
uv run python -c "import sys; sys.path.insert(0,'magnetics-code'); \
from run import run_steps; r=run_steps(199749, channel_filter='Bp_LFS_midplane', \
time_trim=(3.3,3.5), prep_kwargs=dict(cutoff_hz=(5,250), energy=0.98)); \
print('K =', r.condition_number)"

# or execute the whole notebook headless (regenerates its outputs):
uv run --with nbconvert jupyter nbconvert --to notebook --execute --inplace \
    magnetics-code/example_magnetics.ipynb --ExecutePreprocessor.kernel_name=magnetics-uv
```

## Dependencies

Added to the `analysis` uv project: `xarray`, `scipy`, `h5py`, `ipykernel` (all install cleanly on
the pinned Python 3.14). `io_data` reads the shot HDF5 directly with `h5py`.

## Notes & limitations

- The LFS-midplane fit uses the integrated **`MPID66M*`** Bp array (`'Bp_LFS_midplane'`,
  `integrate=False`). For shot 199749 the file has 9 of the 10 sensors (`MPID66M020` is in
  `channels_missing`), which still resolves the low-n structure.
- Reduced χ² runs above 1 because the constant 2e-5 T sensor sigma is optimistic relative to the
  higher-n structure not in the n ≤ 3 basis; the residuals remain small vs. the signals.
- Out of scope (not ported): spectrogram/MODESPEC, 3D coil-current fits, the remote IDL
  `slcontour.py`, Maxwell stress, and internal/external source separation (needs Br, which this
  Bp-only dataset lacks).
