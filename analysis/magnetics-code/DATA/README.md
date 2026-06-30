# Device reference tables

Static reference data for the magnetics analysis, bundled here so `magnetics-code` is fully
self-contained (it does **not** depend on any other directory at runtime).

These are **device** tables (sensor geometry, named sensor/coil subsets, machine wall) — distinct
from the per-shot measurement data in `analysis/data/<shot>/`.

Layout mirrors the source OMFIT magnetics module's `DATA/<device>/`:

```
DATA/DIII-D/
  channel_filters.txt    # named sensor subsets: name = 'regex' ['regex' ...]
  coil_filters.txt       # named 3D-coil subsets (C, IL, IU, 3D_coils)
  channel_alternates.txt # new -> old PTDATA channel-name map (MDSplus fallback; unused locally)
  diiid_sensors.txt      # master sensor geometry table (channel, r, z, phi, tilt, length, ...)
  diiid_bdots.txt        # bdot sensor positions/sizes + former PTDATA names
  diiid.txt              # machine namelist: R0 + &wall (r, z) first-wall outline
```

Loaders live in `../omfit_compat.py`:
`load_channel_filters`, `load_coil_filters`, `list_sensor_subsets`, `resolve_channel_filter`,
`load_sensor_table`, `load_bdot_table`, `load_channel_alternates`, `load_wall`.

Provenance: copied verbatim from the OMFIT magnetics module's `DATA/DIII-D/` tables.
