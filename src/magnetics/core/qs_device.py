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

Kept as a standalone leaf (not folded into ``qs_io_data``) because it is *shared* device
metadata: ``qs_prep``, ``qs_fit``, ``qs_plots`` and ``service.nodes`` all import from it,
not just the shot loader — so a separate module keeps those consumers from depending on
``qs_io_data`` (the HDF5 loader) just to reach ``is_device`` / ``load_wall``.
"""

from __future__ import annotations

import re

import numpy as np
import xarray as xr

from ..data import devices as _devices
from ..data import diiid_geometry as _diiid_geo


def load_device(device: str = "DIII-D") -> dict:
    """The parsed device JSON dict, via the data layer's name/id resolver.

    ``devices.resolve_device_id`` maps a display name (e.g. ``"DIII-D"``) or a config
    id to the JSON file stem using each device file's ``name`` field — so no device
    alias is hardcoded here. Falls back to a slugified name if it can't be resolved.
    """
    dev_id = _devices.resolve_device_id(device) or re.sub(r"[^a-z0-9]", "", str(device).lower())
    return _devices.load_device(dev_id)


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
    ``{r,z,phi,theta}_end1/2`` that the SLCONTOUR fit needs, plus the paired sensor's
    ``pair_{phi,theta,z}_end1/2`` (for the pairwise-difference basis; NaN when unpaired).
    A sensor is modelled as a
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

    # ── paired-sensor ends (for the SLCONTOUR pairwise-difference basis) ──────────
    # A differential sensor (pair != "None") reports field(X) - field(pair); the fit
    # differences the basis at X and at its pair. Resolve each channel's pair to its
    # row and gather the pair's *_end1/2 here (NaN when unpaired/unresolved) so the
    # pair geometry rides the normal geometry-attach path into the fit.
    name_to_row = {c: i for i, c in enumerate(channels)}
    pair_row = np.array([name_to_row.get(str(p), -1) if str(p) != "None" else -1 for p in pairs])

    def _by_pair(arr):
        out = np.full(len(channels), np.nan)
        valid = pair_row >= 0
        out[valid] = arr[pair_row[valid]]
        return out

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
            "pair_phi_end1": ("channel", _by_pair(phi_end1)),
            "pair_phi_end2": ("channel", _by_pair(phi_end2)),
            "pair_theta_end1": ("channel", _by_pair(theta_end1)),
            "pair_theta_end2": ("channel", _by_pair(theta_end2)),
            "pair_z_end1": ("channel", _by_pair(z_end1)),
            "pair_z_end2": ("channel", _by_pair(z_end2)),
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
