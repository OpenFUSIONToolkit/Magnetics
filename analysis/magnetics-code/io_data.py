"""Shot loader — reads the per-shot HDF5 file and the device JSON.

Replaces the old "fetch" step (and the netCDF ``RAW``/``PLASMA_PARAMS``/
``COUPLING`` loader).  Inputs now come from the project-canonical locations:

  * raw sensor signals from ``data/datafile/shot_<shot>.h5``, and
  * device/sensor geometry from ``data/device/<device>.json`` (via
    :mod:`omfit_compat`).

``shot_<shot>.h5`` layout (what the PTDATA fetch produces):
  * one group per fetched channel, each with ``data`` (samples) and ``time``
    (a hard-link into ``_timebases``); **all time is in milliseconds**.
  * a ``_timebases`` group holding the few shared time vectors (channels sample
    at several rates — integrated probes ~50 kHz, bdots ~200 kHz, coils/ip/bt
    ~20 kHz).
  * root attrs: ``device``, ``shot``, ``tmin``/``tmax`` (ms), ``channels_*``.

Because the downstream :mod:`prep`/:mod:`fit` operate on a single
``signal(channel, time)`` matrix, the loader **interpolates every sensor channel
onto one common time axis** — the densest native grid present, clipped to the
window all channels share — and converts that axis to **seconds**.  The global
``ip``/``bt`` traces go into the ``plasma`` Dataset on their native **ms** base.

Sensor geometry (the per-channel ``r,z,phi,theta,...`` and the derived
``*_end1/2`` coordinates the fit needs) is attached from the device JSON; see
:func:`omfit_compat.sensor_geometry`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import xarray as xr

from omfit_compat import list_sensor_subsets, printw, resolve_channel_filter, sensor_geometry

#: Default location of the per-shot HDF5 files (repo ``data/datafile/``; this
#: file lives in ``analysis/magnetics-code/``, so it is two levels up).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DATAFILE_ROOT = os.path.normpath(os.path.join(_THIS_DIR, "..", "..", "data", "datafile"))

#: Groups in the HDF5 file that are not geometry-bearing sensor channels.
_NON_SENSOR_GROUPS = {"_timebases"}
#: Channel groups routed to the ``plasma`` Dataset rather than ``raw``.
_PLASMA_CHANNELS = {"ip": "Ip", "bt": "Bt"}
#: Constant per-channel measurement uncertainty (T) — the documented optimistic
#: sensor sigma the historical data effectively carried.
_DEFAULT_SIGMA = 2.0e-5


@dataclass
class ShotData:
    """Bundle of the input Datasets for one shot."""

    shot: int
    device: str
    raw: xr.Dataset
    plasma: xr.Dataset
    coupling: xr.Dataset | None = None


def shot_path(shot, data_root=DATAFILE_ROOT):
    """Resolve the HDF5 path for ``shot`` (an int/str shot number, or a path)."""
    if os.path.isfile(str(shot)):
        return str(shot)
    return os.path.join(data_root, f"shot_{int(shot)}.h5")


def _read_group(group):
    """Return ``(data, time_ms)`` float arrays for one channel group."""
    return np.asarray(group["data"][:], dtype=float), np.asarray(group["time"][:], dtype=float)


def load_shot(shot, data_root=DATAFILE_ROOT, helicity=-1):
    """Load the ``raw`` (sensors) and ``plasma`` (Ip/Bt) Datasets for ``shot``.

    :param shot: shot number (int/str) or a path to a ``shot_<n>.h5`` file.
    :param data_root: directory holding the ``shot_<n>.h5`` files.
    :param helicity: field/current helicity convention used to orient mode signs
        (default ``-1``; the new data files do not store it).
    :return: :class:`ShotData` (``coupling`` is ``None`` — the new files carry no
        DC vacuum-coupling matrix).
    """
    import h5py

    path = shot_path(shot, data_root)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No shot file at {path!r}")

    with h5py.File(path, "r") as fh:
        device = _attr_str(fh.attrs.get("device", "DIII-D"))
        shot_no = int(np.atleast_1d(fh.attrs.get("shot", _shot_from_path(path)))[0])

        geo = sensor_geometry(device)
        geo_channels = set(str(c) for c in geo["channel"].values)

        sensor_sigs, sensor_times, sensor_names = {}, {}, []
        plasma_sigs, plasma_times = {}, {}
        for name in fh:
            if name in _NON_SENSOR_GROUPS:
                continue
            data, t_ms = _read_group(fh[name])
            if name in _PLASMA_CHANNELS:
                plasma_sigs[name] = data
                plasma_times[name] = t_ms
                continue
            if name not in geo_channels:
                printw(f"Channel {name!r} has no geometry in {device} device file -> skipping")
                continue
            sensor_names.append(name)
            sensor_sigs[name] = data
            sensor_times[name] = t_ms / 1.0e3  # ms -> seconds

    if not sensor_names:
        raise ValueError(f"No geometry-bearing sensor channels found in {path!r}")

    raw = _build_raw(sensor_names, sensor_sigs, sensor_times, geo, shot_no, device)
    plasma = _build_plasma(plasma_sigs, plasma_times, helicity)

    return ShotData(shot=shot_no, device=device, raw=raw, plasma=plasma, coupling=None)


def _build_raw(names, sigs, times, geo, shot_no, device):
    """Assemble the ``raw`` Dataset by interpolating channels onto one time axis."""
    # Densest native grid (most samples), clipped to the window all channels share.
    ref = max(names, key=lambda c: times[c].size)
    lo = max(t[0] for t in times.values())
    hi = min(t[-1] for t in times.values())
    ref_t = times[ref]
    grid = ref_t[(ref_t >= lo) & (ref_t <= hi)]
    if grid.size == 0:
        raise ValueError("Channels share no overlapping time window")

    signal = np.empty((len(names), grid.size), dtype=np.float32)
    for i, c in enumerate(names):
        signal[i] = np.interp(grid, times[c], sigs[c])

    raw = xr.Dataset(
        {"signal": (("channel", "time"), signal)},
        coords={"channel": names, "time": grid},
    )

    # Attach per-channel geometry (base + derived ends) from the device file.
    geo_sel = geo.sel(channel=names)
    for var in geo_sel.variables:
        if var == "channel":
            continue
        raw[var] = geo_sel[var]

    raw["signal_sigma"] = ("channel", np.full(len(names), _DEFAULT_SIGMA))
    raw.attrs.update(shot=shot_no, device=device, sigma_type=_DEFAULT_SIGMA)
    return raw


def _build_plasma(sigs, times, helicity):
    """Assemble the ``plasma`` Dataset (Ip/Bt on a shared ms time base)."""
    if not sigs:
        plasma = xr.Dataset(coords={"time": np.array([], dtype=float)})
        plasma.attrs["helicity"] = int(helicity)
        return plasma

    base = "ip" if "ip" in times else next(iter(times))
    t_ms = times[base]
    data_vars = {}
    for name, var in _PLASMA_CHANNELS.items():
        if name not in sigs:
            continue
        y = sigs[name] if np.array_equal(times[name], t_ms) else np.interp(t_ms, times[name], sigs[name])
        data_vars[var] = ("time", y)

    plasma = xr.Dataset(data_vars, coords={"time": t_ms})
    plasma.attrs["helicity"] = int(helicity)
    return plasma


def _attr_str(v):
    """Decode an HDF5 attribute to a plain string."""
    v = np.atleast_1d(v)[0] if np.ndim(v) else v
    return v.decode() if isinstance(v, bytes) else str(v)


def _shot_from_path(path):
    """Best-effort shot number from a ``shot_<n>.h5`` filename."""
    stem = os.path.splitext(os.path.basename(path))[0]
    digits = "".join(ch for ch in stem if ch.isdigit())
    return int(digits) if digits else 0


def available_subsets(device="DIII-D"):
    """All named sensor subsets you can pass as ``channel_filter``.

    Thin convenience over :func:`omfit_compat.list_sensor_subsets` -> a
    ``{name: [sensor, ...]}`` mapping (e.g. ``'Bp_LFS_midplane'``, ``'All_3D_Coils'``).
    Names work with or without underscores.
    """
    return list_sensor_subsets(device)


def valid_channels(raw, channel_filter=".*", device="DIII-D"):
    """Channel names matching ``channel_filter`` that carry non-NaN signal.

    ``channel_filter`` may be a regex, a list of regexes, or a friendly subset
    name from the device file (e.g. ``'Bp_LFS_midplane'``, ``'All_3D_Coils'``);
    see :func:`available_subsets`.
    """
    import re

    patterns = resolve_channel_filter(channel_filter, device)
    out = []
    for c in raw["channel"].values:
        if any(re.match(p, c) for p in patterns):
            if not np.all(np.isnan(raw["signal"].sel(channel=c).values)):
                out.append(c)
    return out
