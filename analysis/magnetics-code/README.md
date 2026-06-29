# magnetics-code — local OMFIT magnetics translation (3D spatial fits)

A standalone, OMFIT-free translation of the OMFIT magnetics **3D spatial-fit** workflow — the
SLCONTOUR-style quasi-stationary modal decomposition of locked / slowly-rotating MHD modes
(VISION.md §4.1). It runs locally (no OMFIT, no MDSplus) against the example netCDF data in
`../data/<shot>/`.

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
| `io_data.py` | `load_shot` reads RAW / PLASMA_PARAMS / COUPLING netCDF (the "fetch" step) | `fetch_magnetics.py` |
| `prep.py` | trim, DC-comp, integrate, causal filter, detrend, SVD-condition | `prep_magnetics.py` |
| `fit.py` | basis matrix + SVD least-squares modal fit | `fit_magnetics.py` |
| `run.py` | `run_steps` orchestrator (load → prep → fit) | `run_magnetics.py` |
| `plots.py` | sensor map, signals, fit quality, mode amp/phase, φ-vs-time contour, SVD diagnostics | `plot_magnetics_*.py` |
| `omfit_compat.py` | shim for OMFIT-runtime symbols (`printi`, `cornernote`, `uband`, `is_device`, subset filters, wall) | (OMFIT framework) |

This package is **fully self-contained**: it has no runtime dependency on any other directory and
runs even if the source OMFIT module is absent. Device reference tables (sensor geometry, named
subsets, wall) are bundled under [`DATA/DIII-D/`](DATA/README.md) — see the next section.

## Data

The example shots live in `../data/<shot>/` as three netCDF (HDF5) files — the Datasets that
`fetch_magnetics.py` normally builds from MDSplus:

- `RAW` — `signal(channel, time)` + per-channel geometry (`*_end1/2` already derived), `signal_sigma`.
- `PLASMA_PARAMS` — `Bt`, `Ip` (time base in **ms**), `helicity` attr.
- `COUPLING` — `dc_coupling(coil, channel)` DC vacuum-compensation matrix (used only by `prep`'s DC compensation).

`RAW` time is in **seconds**; `prep` aligns the ms plasma traces to it.

## Quick start

```python
import sys; sys.path.insert(0, '.')        # the modules are a flat set, not a package
from run import run_steps
import plots

# load → prep → fit the LFS-midplane toroidal Bp array for n = 1,2,3
r = run_steps(154551, channel_filter='Bp_LFS_midplane', ns=(1, 2, 3), ms=(0,),
              time_trim=(2.5, 4.2), prep_kwargs=dict(cutoff_hz=(5, 250), energy=0.98))

print('condition number K =', r.condition_number)
plots.plot_fit_modes(r.fit)                 # amplitude & phase of each mode vs time
plots.plot_slice(r.fit, fix_coord='theta')  # the SLCONTOUR φ-vs-time contour
```

`channel_filter` accepts a regex, a list of regexes, or a friendly subset name (e.g.
`'Bp_LFS_midplane'`, `'Bp_LFS_R+1'`, `'Bp_All'`, `'3D_coils'`). List them all with
`io_data.available_subsets('DIII-D')`.

## Device reference tables — `DATA/DIII-D/`

Bundled with the package (provenance in [`DATA/README.md`](DATA/README.md)) so it is self-contained.
These are **device** tables, distinct from the per-shot data in `../data/<shot>/`:

| file | content | loader (`omfit_compat`) |
|---|---|---|
| `channel_filters.txt` | named sensor subsets (`Bp_LFS_midplane`, `Bp_All`, …) | `load_channel_filters` |
| `coil_filters.txt` | named 3D-coil subsets (`C`, `IL`, `IU`, `3D_coils`) | `load_coil_filters` |
| `diiid_sensors.txt` | master sensor geometry (`r, z, phi, tilt, length, …`) | `load_sensor_table` |
| `diiid_bdots.txt` | bdot sensor positions/sizes | `load_bdot_table` |
| `channel_alternates.txt` | new→old PTDATA name map | `load_channel_alternates` |
| `diiid.txt` | machine `R0` + `&wall` outline | `load_wall` |

`resolve_channel_filter` / `list_sensor_subsets` merge the sensor **and** coil tables, so every name
in either is a valid `channel_filter`. The fit currently takes geometry from the RAW netCDF;
`load_sensor_table` is a reference loader (deriving the `*_end` coordinates — the `init` step — is
future work, only needed if a shot file ever lacks geometry).

## The worked example

`example_154551.ipynb` walks the full pipeline on **DIII-D 154551** (VISION's reference "rotating
n=1 that slows and locks"). It produces: the sensor map, conditioned signals, data/design-matrix
SVD diagnostics, fit quality, the mode amplitude & phase vs time (rotating → locking), and the
φ-vs-time contour.

Run it on the uv environment (Python 3.14):

```bash
cd analysis
# one-time: register the uv venv as a Jupyter kernel
uv run --with ipykernel python -m ipykernel install --user --name magnetics-uv --display-name "Magnetics (uv 3.14)"
# then either open it in Jupyter and pick the "Magnetics (uv 3.14)" kernel ...
uv run --with jupyterlab jupyter lab magnetics-code/example_154551.ipynb
# ... or execute headless:
uv run --with nbconvert jupyter nbconvert --to notebook --execute --inplace \
    magnetics-code/example_154551.ipynb --ExecutePreprocessor.kernel_name=magnetics-uv
```

## Dependencies

Added to the `analysis` uv project: `xarray`, `scipy`, `h5netcdf`, `h5py`, `ipykernel` (all install
cleanly on the pinned Python 3.14). `io_data` prefers the `h5netcdf` engine and falls back to a
backend-free `h5py` loader if no netCDF backend is available.

## Notes & limitations

- The example `RAW` carries the integrated **`MPID*`** Bp signals (the raw `MPI66M*D` bdot channels
  are empty in this file), so the LFS-midplane fit uses `'MPID66M.*'` (10 sensors, resolves |n| ≤ 4)
  with `integrate=False`.
- Reduced χ² runs above 1 because the constant 2e-5 T sensor sigma is optimistic relative to the
  higher-n structure not in the n ≤ 3 basis; the residuals remain small vs. the signals.
- Out of scope (not ported): spectrogram/MODESPEC, 3D coil-current fits, the remote IDL
  `slcontour.py`, Maxwell stress, and internal/external source separation (needs Br, which this
  Bp-only dataset lacks).
