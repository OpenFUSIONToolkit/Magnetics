# Quasi-stationary mode analysis (SLCONTOUR-style) — pipeline details

The **quasi-stationary** path analyses locked and slowly-rotating MHD modes by fitting the *spatial*
pattern of the perturbed field measured by a sensor **array** (VISION.md §4.1). At each time slice it
decomposes δB(φ, θ) into a small set of toroidal/poloidal harmonics by SVD-conditioned least squares,
and reports the design-matrix **condition number K** (the central trust metric — warn K > 10, error
K > 20), per-coefficient error bars, and reduced χ².

It runs entirely off the project-canonical data — per-shot signals in `data/datafile/shot_<n>.h5`
and device geometry in `data/device/<device>.json` — with no MDSplus or external framework.

The fit basis (cylindrical geometry) is

```
δB(φ, θ) = Σ_nm  b_nm · exp(i(nφ + mθ))
```

> **Scope.** This is the spatial fit of sensor *arrays*. The rotating-mode spectrogram / MODESPEC
> path (`magnetics.core.spectral`) and 3D coil-current fits are separate and out of scope here.

## The pipeline (`magnetics.core.qs_*`)

All modules live in `src/magnetics/core/` under the unified `qs_` prefix:

| module | role |
|---|---|
| `qs_io_data.load_shot` | read `shot_<n>.h5` signals and join the per-channel device geometry → the `raw` / `plasma` Datasets |
| `qs_prep.prepare` | trim (channels + time), optional integrate (bdot→B), causal band/high/low-pass, detrend, SVD-condition the data matrix |
| `qs_fit.fit` | build the design matrix from the basis, SVD it (K + error bars), least-squares fit every time slice → the `fit` Dataset |
| `qs_run.run_steps` | the `load → prep → fit` orchestrator; returns a `MagneticsRun` bundling `raw` / `prepared` / `plasma` / `fit` (+ `condition_number`) |
| `qs_device` | device-JSON readers — `sensor_geometry` (base + derived `theta`/`*_end1/2`), `resolve_channel_filter`, `list_sensor_subsets`, `load_wall` — **delegating to the `data/` layer** (`data.devices`, `data.diiid_geometry`) |
| `qs_bridge` | adapt the `fit` Dataset → GUI `kind`-nodes — the **production/service** output path |
| `qs_plots` | standalone **matplotlib** plots (sensor map, signals, SVD diagnostics, fit quality, mode amp/phase, φ-vs-time contour) — for notebooks/offline use, **not** wired into the GUI |

There are two consumers of the `fit` Dataset. The **service** builds JSON nodes from it via
`qs_bridge` (served by `service/nodes.py` → the GUI's QS tab). The **notebook/offline** path renders
it directly with `qs_plots`. They share the same physics and the same reconstruction sign convention
(below); `qs_bridge` does not import `qs_plots`.

## Data inputs

### Per-shot signals — `data/datafile/shot_<n>.h5`

One HDF5 file per shot (the PTDATA fetch output): a group per channel with `data` + `time`
(hard-linked into a shared `_timebases` group), **all time in milliseconds**. Channels sample at
several rates (integrated probes ~50 kHz, bdots ~200 kHz, coils/`ip`/`bt` ~20 kHz). Root attrs
include `device`, `shot`, `tmin`/`tmax` (ms).

`qs_io_data.load_shot` turns this into the Datasets the pipeline expects:

- `raw` — `signal(channel, time)` (time in **seconds**), `signal_sigma` (a constant 2e-5 T), and the
  per-channel geometry joined from the device JSON, including the derived `*_end1/2` coordinates. All
  sensor channels are interpolated onto one common time axis (the densest native grid, clipped to the
  window they share).
- `plasma` — `Ip`, `Bt` from the `ip`/`bt` channels (time in **ms**), and a `helicity` attr computed
  as sign(Bt·Ip) from those traces (−1 fallback when they're absent).
- `coupling` — `None`; the new files carry no DC vacuum-coupling matrix, so `qs_prep`'s DC
  compensation (`dc_comp=True`) is unavailable.

### Device geometry — `data/device/<device>.json`

The canonical device description (`diiid.json` for DIII-D): `R0`, the shot-segmented `first_wall`
outline, the per-sensor base geometry (`r, z, phi, tilt, length, delta_phi, na, pair`), and named
`sensor_sets`. `qs_device` reads it through the shared `data.devices` resolvers (so the QS pipeline
and the fetcher never disagree about a shot's geometry) and adds the QS-specific derived `theta` and
`*_end1/2` sensor-end coordinates in `sensor_geometry`.

## Quick start

The project is a `uv` package rooted at the repo; import `magnetics.core.qs_*` directly (no
`sys.path` juggling):

```python
from magnetics.core.qs_run import run_steps
from magnetics.core import qs_plots as plots

# load → prep → fit the LFS-midplane toroidal Bp array for n = 1,2,3
r = run_steps(199749, channel_filter="Bp_LFS_midplane", ns=(1, 2, 3), ms=(0,),
              time_trim=(3.3, 3.5), prep_kwargs=dict(cutoff_hz=(5, 250), energy=0.98))

print("condition number K =", r.condition_number)
plots.plot_fit_modes(r.fit)                 # amplitude & phase of each mode vs time
plots.plot_slice(r.fit, fix_coord="theta")  # the SLCONTOUR φ-vs-time contour
```

`channel_filter` accepts a regex, a list of regexes, or a friendly subset name — with or without
underscores (e.g. `"Bp_LFS_midplane"` or `"Bp LFS midplane"`, `"Bp_All"`, `"All_3D_Coils"`). List
them all with `qs_io_data.available_subsets("DIII-D")`. `time_trim` must fall inside the shot file's
window (shot 199749 spans **3.3–3.5 s**).

The worked, shot-configurable notebook is [`examples/example_magnetics.ipynb`](../examples/example_magnetics.ipynb)
(needs a fetched `shot_<n>.h5`; the repo ships no tokamak data).

## Reconstruction sign convention

The fit basis is `exp(+i(nφ + mθ))`, but each complex basis column is split into two *real*
least-squares columns and the complex coefficient is reassembled as `b = x_r + i·x_i`. Because of
that split, the field that reproduces the fitted signal is

```
δB(φ, θ) = Re Σ_nm  b_nm · exp(−i(nφ + mθ))
```

i.e. **reconstruction uses `exp(−i(…))`** even though the fit basis is `+i`. This is honoured by
`qs_bridge._reconstruct_grid` / `fit_to_phi_t_node` and `qs_plots.plot_slice` (and matches the DIII-D
SLCONTOUR reference). Do not "align" the reconstruction to `+i` — that mirrors the toroidal phase and
flips helicity. A regression test in `tests/test_qs_bridge.py` pins this.

## Notes & limitations

- Reduced χ² typically runs above 1 because the constant 2e-5 T sensor σ is optimistic relative to
  higher-n structure not in the basis; residuals stay small versus the signals. Per-sensor σ from the
  data layer is an open item (helicity is now computed from the shot's Ip·Bt in `qs_io_data`).
- The pure-numpy relatives of `qs_fit` (a device-agnostic `core` port) and the `data/`-layer
  set-flattening dedup are open follow-ups.
- Out of scope for this path: the rotating-mode spectrogram/MODESPEC analysis, 3D coil-current fits,
  and internal/external source separation (needs Br, which a Bp-only array lacks).
