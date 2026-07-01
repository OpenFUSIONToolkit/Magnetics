"""QS device adapter — sensor geometry + channel-set resolution for the SLCONTOUR fit.

Self-contained for the quasi-stationary (``qs_*``) pipeline, but **delegates to the
data layer** for everything the data layer already owns: JSON loading and shot-aware
segment resolution (:mod:`magnetics.data.devices`) and sensor-set flattening
(:mod:`magnetics.data.diiid_geometry`). It adds only the QS-specific pieces the fit
needs and that have no home in ``data/``:

  * :func:`sensor_geometry` — the derived poloidal angle ``theta`` and the sensor-end
    coordinates ``{r,z,phi,theta}_end1/2`` assembled as an ``xarray.Dataset``;
  * :func:`resolve_channel_filter` — the fit/prep channel-filter semantics (friendly
    subset name → anchored regex list; unknown string passed through as a raw regex);
  * :func:`is_device` — the loose device-name comparison the fit/prep steps use.

Replaces the old ``_slcontour/omfit_compat.py`` OMFIT shim (deleted). This module does
not read the device JSON itself — it routes through ``data.devices`` so the QS pipeline
and the fetcher can never disagree about a shot's geometry.
"""

from __future__ import annotations

import re

import numpy as np
import xarray as xr

from ..data import devices as _devices
from ..data import diiid_geometry as _diiid_geo

# ``data.devices.load_device`` resolves ``<name>.json`` by lowercasing the name; a few
# display names don't slugify by lowercasing alone (``"DIII-D"`` → ``diiid.json``, not
# ``diii-d.json``). Preserve the alias the old shim carried.
_DEVICE_ALIAS = {"DIII-D": "diiid"}


def _device_key(device: str) -> str:
    """Map a device display name to its ``data/device/<key>.json`` stem."""
    if device in _DEVICE_ALIAS:
        return _DEVICE_ALIAS[device]
    return re.sub(r"[^a-z0-9]", "", str(device).lower())


def load_device(device: str = "DIII-D") -> dict:
    """The parsed device JSON dict, via the data layer (with QS name aliasing)."""
    return _devices.load_device(_device_key(device))


# ── device-name comparison ─────────────────────────────────────────────────────


def is_device(device, name) -> bool:
    """Loose device-name equality (``DIII-D`` == ``DIIID`` == ``diii_d``)."""

    def _norm(s):
        return re.sub(r"[^a-z0-9]", "", str(s).lower())

    return _norm(device) == _norm(name)


# ── sensor-set resolution (reuses data/diiid_geometry flattening) ───────────────


def _norm_name(name):
    """Normalise a subset name so ``'Bp_LFS_midplane'`` == ``'Bp LFS midplane'``."""
    return str(name).strip().replace("_", " ")


def _subsets(device="DIII-D") -> dict[str, list[str]]:
    """``{set_name: [sensor, ...]}`` for every named set (composites flattened).

    Reuses the data layer's set-flattening (``diiid_geometry._build_sets``) rather
    than carrying a fourth copy of the recursion/dedup logic.
    """
    sets = load_device(device).get("sensor_sets", {})
    return {s["name"]: s["sensors"] for s in _diiid_geo._build_sets(sets)}


def list_sensor_subsets(device="DIII-D"):
    """All named sensor subsets → ``{name: [sensor, ...]}`` (composites flattened).

    Every key here is a valid ``channel_filter`` argument (with or without underscores).
    """
    return _subsets(device)


def resolve_channel_filter(channel_filter, device="DIII-D"):
    """Map a friendly subset name (e.g. ``'Bp_LFS_midplane'``) to a pattern list.

    A known subset name resolves to the explicit, anchored sensor names from the
    device ``sensor_sets``; an unknown string is treated as a raw regex and passed
    through. Lists/tuples expand each element the same way. Patterns are matched
    downstream with :func:`re.match`, so resolved names are anchored with ``$`` to
    avoid accidental prefix matches (e.g. ``C19`` vs ``C190``).
    """
    subsets = _subsets(device)
    lookup = {_norm_name(k): k for k in subsets}

    def resolve_one(cf):
        if isinstance(cf, str):
            key = lookup.get(_norm_name(cf))
            if key is not None:
                return [re.escape(s) + "$" for s in subsets[key]]
            return [cf]  # raw regex
        return [cf]

    if isinstance(channel_filter, str):
        return resolve_one(channel_filter)
    out = []
    for cf in channel_filter:
        out += resolve_one(cf)
    return out


# ── sensor geometry (QS-unique: derived theta + sensor-end coordinates) ─────────


def _to_float(s):
    try:
        return float(s)
    except TypeError, ValueError:
        return float("nan")


def sensor_geometry(device="DIII-D", shot=None):
    """Per-sensor geometry as an ``xarray.Dataset`` indexed by ``channel``.

    Base fields (``r, z, phi, tilt, length, delta_phi, na``, plus ``pair``) come from
    the data layer's shot-aware resolver (:func:`devices.geometry_nearest`); this
    function adds the derived poloidal angle ``theta`` and the sensor-end coordinates
    ``{r,z,phi,theta}_end1/2`` that the SLCONTOUR fit needs. A sensor is modelled as a
    straight segment of physical ``length`` centred at ``(r, z)`` tilted by ``tilt``
    (degrees) in the poloidal plane and spanning ``delta_phi`` (degrees) toroidally;
    angles are measured about the magnetic axis at ``(R0, 0)``.

    ``shot`` selects the shot-correct hardware segment; ``None`` falls back to each
    sensor's earliest segment (layout view). All device channels are returned, with
    NaN geometry for any the device file does not model at ``shot``.
    """
    dev = load_device(device)
    R0 = float(dev["R0"])
    channels = list(dev.get("sensors", {}))
    lookup_shot = 0 if shot is None else int(shot)

    base = ["r", "z", "phi", "tilt", "length", "delta_phi", "na"]
    cols = {k: [] for k in base}
    pairs = []
    for c in channels:
        g = _devices.geometry_nearest(dev, c, lookup_shot) or {}
        for k in base:
            cols[k].append(_to_float(g.get(k, np.nan)))
        pairs.append(g.get("pair", "None"))
    cols = {k: np.array(v, dtype=float) for k, v in cols.items()}
    pairs = np.array(pairs, dtype=object)

    r, z, phi = cols["r"], cols["z"], cols["phi"]
    tilt, length, delta_phi = cols["tilt"], cols["length"], cols["delta_phi"]
    half = length / 2.0
    tr = np.radians(tilt)

    theta = np.degrees(np.arctan2(z, r - R0))
    r_end1, r_end2 = r - half * np.cos(tr), r + half * np.cos(tr)
    z_end1, z_end2 = z - half * np.sin(tr), z + half * np.sin(tr)
    phi_end1, phi_end2 = phi - delta_phi / 2.0, phi + delta_phi / 2.0
    theta_end1 = np.degrees(np.arctan2(z_end1, r_end1 - R0))
    theta_end2 = np.degrees(np.arctan2(z_end2, r_end2 - R0))

    ds = xr.Dataset(
        {
            **{k: ("channel", cols[k]) for k in base},
            "theta": ("channel", theta),
            "r_end1": ("channel", r_end1),
            "r_end2": ("channel", r_end2),
            "z_end1": ("channel", z_end1),
            "z_end2": ("channel", z_end2),
            "phi_end1": ("channel", phi_end1),
            "phi_end2": ("channel", phi_end2),
            "theta_end1": ("channel", theta_end1),
            "theta_end2": ("channel", theta_end2),
        },
        coords={"channel": channels},
    )
    ds["pair"] = ("channel", pairs)
    ds.attrs["device"] = device
    ds.attrs["R0"] = R0
    return ds


# ── first-wall outline (delegates to the data layer's segmented reader) ─────────


def load_wall(device="DIII-D", shot=None):
    """The ``(r, z)`` first-wall outline arrays for ``device`` at ``shot``.

    Delegates to :func:`devices.feature_at` for the shot-segmented ``first_wall`` key,
    returning ``(None, None)`` when no device file or wall segment is found. (The old
    shim read a nonexistent top-level ``wall`` key and returned ``(None, None)`` for
    every shipped device; this returns the real outline.)
    """
    try:
        dev = load_device(device)
    except FileNotFoundError, OSError, ValueError:
        return None, None
    fw = _devices.feature_at(dev, "first_wall", 0 if shot is None else int(shot))
    if not fw or "r" not in fw or "z" not in fw:
        return None, None
    return np.array(fw["r"], dtype=float), np.array(fw["z"], dtype=float)
