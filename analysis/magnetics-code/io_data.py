"""Local replacement for ``SCRIPTS/fetch_magnetics.py`` (the MDSplus fetch).

In OMFIT, ``fetch`` pulls every requested channel from MDSplus and assembles the
``INPUTS/RAW``, ``INPUTS/PLASMA_PARAMS`` and ``INPUTS/COUPLING`` ``xarray``
Datasets.  Here the example data has already been fetched and saved to netCDF
(``analysis/data/<shot>/{RAW,PLASMA_PARAMS,COUPLING}``), with the per-channel
geometry already derived by ``init_magnetics.py``.  So "fetch" is just a loader.

``RAW`` layout (what ``fetch_magnetics.py`` produces):
  dims  : channel (192) x time (204800, seconds)
  vars  : signal(channel,time), signal_sigma(channel),
          and per-channel geometry r,z,phi,theta,tilt,length,delta_phi,na,pair,
          plus the sensor-end coordinates *_end1/*_end2.
  attrs : shot, device, sigma_type

``PLASMA_PARAMS`` : Bt, Ip on a time base in **milliseconds**, attr helicity.
``COUPLING``      : dc_coupling(coil, channel) DC vacuum-compensation matrix.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import xarray as xr

#: Default location of the example shot directories.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = os.path.normpath(os.path.join(_THIS_DIR, "..", "data"))


@dataclass
class ShotData:
    """Bundle of the three input Datasets for one shot."""

    shot: int
    device: str
    raw: xr.Dataset
    plasma: xr.Dataset
    coupling: xr.Dataset | None = None


def _open(path):
    """Open a netCDF/HDF5 file as an xarray Dataset.

    Tries the standard backends; if no compiled netCDF backend is usable it
    falls back to reading the HDF5 directly with h5py and rebuilding the
    Dataset.  These files are netCDF4 (== HDF5), so the fallback is lossless.
    """
    for engine in ("h5netcdf", "netcdf4"):
        try:
            return xr.load_dataset(path, engine=engine)
        except (ValueError, ImportError, OSError):
            continue
    return _open_with_h5py(path)


def _open_with_h5py(path):
    """Backend-free fallback loader using h5py (handles the netCDF4 dim scales)."""
    import h5py

    with h5py.File(path, "r") as fh:
        # dimension scales (CLASS == DIMENSION_SCALE) become coordinates
        dim_names = [k for k in fh if fh[k].attrs.get("CLASS", b"") == b"DIMENSION_SCALE"]

        def _decode(arr):
            if arr.dtype.kind in ("S", "O"):
                return np.array([v.decode() if isinstance(v, bytes) else v for v in arr])
            return arr[:]

        # map each dataset's dimensions via its attached DIMENSION_LIST refs
        def _dims_for(dset):
            dl = dset.attrs.get("DIMENSION_LIST")
            if dl is None:
                # a dimension scale indexes itself
                return (dset.name.lstrip("/"),)
            dims = []
            for refs in dl:
                ref = refs[0] if np.ndim(refs) else refs
                dims.append(fh[ref].name.lstrip("/"))
            return tuple(dims)

        coords = {name: _decode(fh[name]) for name in dim_names}
        data_vars = {}
        for k in fh:
            if k in dim_names:
                continue
            dset = fh[k]
            data_vars[k] = (_dims_for(dset), _decode(dset))
        attrs = {k: _scalar(v) for k, v in fh.attrs.items() if not k.startswith("_NC")}
        ds = xr.Dataset(data_vars=data_vars, coords=coords, attrs=attrs)
    return ds


def _scalar(v):
    """Unwrap length-1 arrays / bytes from HDF5 attributes."""
    if isinstance(v, bytes):
        return v.decode()
    arr = np.atleast_1d(v)
    return arr[0] if arr.size == 1 else v


def load_shot(shot, data_root=DATA_ROOT):
    """Load the RAW / PLASMA_PARAMS / COUPLING Datasets for ``shot``.

    :param shot: shot number (int) or a path to the shot directory.
    :param data_root: directory containing the per-shot subfolders.
    :return: :class:`ShotData`.
    """
    shot_dir = shot if os.path.isdir(str(shot)) else os.path.join(data_root, str(shot))
    if not os.path.isdir(shot_dir):
        raise FileNotFoundError(f"No shot directory at {shot_dir!r}")

    raw = _open(os.path.join(shot_dir, "RAW"))
    plasma = _open(os.path.join(shot_dir, "PLASMA_PARAMS"))

    coupling_path = os.path.join(shot_dir, "COUPLING")
    coupling = _open(coupling_path) if os.path.exists(coupling_path) else None

    shot_no = int(np.atleast_1d(raw.attrs.get("shot", os.path.basename(shot_dir)))[0])
    device = str(raw.attrs.get("device", "DIII-D"))

    # Normalise the channel coordinate to plain python strings for clean regex/sel.
    if raw["channel"].dtype.kind in ("S", "O"):
        raw = raw.assign_coords(channel=[str(c) for c in raw["channel"].values])

    # PLASMA_PARAMS carries the helicity convention used by the fit.
    if "helicity" not in plasma.attrs:
        plasma.attrs["helicity"] = int(np.atleast_1d(plasma.attrs.get("helicity", -1))[0])

    return ShotData(shot=shot_no, device=device, raw=raw, plasma=plasma, coupling=coupling)


def available_subsets(device="DIII-D"):
    """All named sensor/coil subsets you can pass as ``channel_filter``.

    Thin convenience over :func:`omfit_compat.list_sensor_subsets` -> a
    ``{name: [regex, ...]}`` mapping (e.g. ``'Bp_LFS_midplane'``, ``'3D_coils'``).
    """
    from omfit_compat import list_sensor_subsets

    return list_sensor_subsets(device)


def valid_channels(raw, channel_filter=".*", device="DIII-D"):
    """Channel names matching ``channel_filter`` that carry non-NaN signal.

    ``channel_filter`` may be a regex, a list of regexes, or a friendly subset
    name from the device tables (e.g. ``'Bp_LFS_midplane'``, ``'3D_coils'``);
    see :func:`available_subsets`.
    """
    import re

    from omfit_compat import resolve_channel_filter

    patterns = resolve_channel_filter(channel_filter, device)
    out = []
    for c in raw["channel"].values:
        if any(re.match(p, c) for p in patterns):
            if not np.all(np.isnan(raw["signal"].sel(channel=c).values)):
                out.append(c)
    return out
