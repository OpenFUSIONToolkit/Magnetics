"""Compatibility shim for the OMFIT runtime symbols used by the magnetics scripts.

The OMFIT magnetics module runs inside the OMFIT
framework, which injects a large namespace (``root[...]``, ``defaultVars``,
``OMFITx``, ``printi``/``printw``, ``cornernote``, ``uband``, ``is_device`` ...)
into every script.  When we port those scripts to run locally we only need a
small subset of that namespace.  This module reimplements exactly that subset so
the ported ``prep`` / ``fit`` / ``plots`` code reads almost identically to the
OMFIT originals.

Nothing here talks to MDSplus, OMFIT, or a remote server.
"""

from __future__ import annotations

import os
import re

import numpy as np

# --------------------------------------------------------------------------- #
# Console messaging (OMFIT's printi/printv/printw/printe)
# --------------------------------------------------------------------------- #
# In OMFIT these route to the GUI console with severity colouring.  Locally we
# just print, with a severity prefix for the warnings/errors.


def printi(*args):
    """Informational message."""
    print(*args)


def printv(*args):
    """Verbose message (same as printi locally)."""
    print(*args)


def printw(*args):
    """Warning message."""
    print("WARNING:", *args)


def printe(*args):
    """Error/alert message (non-fatal, like the OMFIT original)."""
    print("ERROR:", *args)


class OMFITexception(Exception):
    """Local stand-in for omfit_classes.exceptions_omfit.OMFITexception."""


# --------------------------------------------------------------------------- #
# Small numeric helpers OMFIT provides in its namespace
# --------------------------------------------------------------------------- #


def is_device(device, name):
    """Loose device-name comparison (OMFIT's omfit_classes.utils_base.is_device).

    Treats ``DIII-D`` / ``DIIID`` / ``diii_d`` as equivalent.
    """

    def _norm(s):
        return re.sub(r"[^a-z0-9]", "", str(s).lower())

    return _norm(device) == _norm(name)


def _delta_degrees_scalar(theta1, theta2):
    """Angular width from theta1 to theta2 in degrees, wrapping once through 0."""
    dt = theta2 - theta1
    if dt > 180:
        dt -= 360
    if dt < -180:
        dt += 360
    return dt


#: Vectorised version, matching ``delta_degrees`` in fit_magnetics.py.
delta_degrees = np.vectorize(_delta_degrees_scalar)


# --------------------------------------------------------------------------- #
# Plot helpers (OMFIT's cornernote and uband)
# --------------------------------------------------------------------------- #


def cornernote(ax=None, device="", shot="", time="", text="", **_ignore):
    """Annotate the bottom-right corner with shot/device context.

    Mirrors omfit_classes.utils_plot.cornernote: a small grey label in the
    figure corner.  Extra keyword arguments (e.g. ``root=``) are accepted and
    ignored for call-site compatibility.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        ax = plt.gca()
    fig = ax.get_figure()
    label = " ".join(str(s) for s in (device, shot, time, text) if str(s) != "")
    if not label:
        return
    fig.text(
        0.99,
        0.01,
        label,
        ha="right",
        va="bottom",
        fontsize=8,
        color="0.4",
    )


def uband(x, y, yerr, ax=None, label=None, color=None, **kwargs):
    """Plot a line with a shaded +/- uncertainty band.

    Local replacement for omfit_classes.utils_plot.uband, which takes an
    ``uncertainties`` ``unumpy`` array.  Here we pass the nominal values ``y``
    and their standard deviation ``yerr`` explicitly to avoid the extra
    dependency.

    Returns a one-tuple ``(line,)`` so call sites can write ``(l,) = uband(...)``
    exactly as in the OMFIT plots.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        ax = plt.gca()
    x = np.asarray(x)
    y = np.asarray(y, dtype=float)
    yerr = np.asarray(yerr, dtype=float)
    (line,) = ax.plot(x, y, label=label, color=color, **kwargs)
    ax.fill_between(
        x,
        y - yerr,
        y + yerr,
        color=line.get_color(),
        alpha=0.3,
        linewidth=0,
    )
    return (line,)


# --------------------------------------------------------------------------- #
# Device reference data (sensor geometry / wall / named subsets)
# --------------------------------------------------------------------------- #
# All device metadata now comes from the project-canonical ``data/device/<slug>.json``
# (e.g. ``diiid.json``), replacing the old bundled ``DATA/<device>/*.txt`` tables.
# That single JSON carries ``R0``, the first-wall outline, the per-sensor base
# geometry and the named ``sensor_sets`` used to resolve a ``channel_filter``.

import json

#: Root of the canonical device files — the package's single source of truth
#: (``magnetics/data/device/``), resolved through the data layer.
from ..data import devices as _devices

DEVICE_DIR = str(_devices.DEVICE_DIR)

#: Explicit device-name -> json-filename overrides; otherwise slugified.
_DEVICE_FILE = {"DIII-D": "diiid.json"}

_device_cache = {}


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return float("nan")


def _segment_fields(rec, shot=None):
    """The geometry fields of a sensor record active at ``shot``.

    The device JSON is shot-segmented (each sensor is ``{"segments": [{since_shot,
    r, z, ...}]}``); a segment is valid from its ``since_shot`` until the next.
    Returns the segment active at ``shot`` (the latest whose ``since_shot`` ≤ shot),
    falling back to the earliest segment for a ``shot`` before any campaign (a
    layout fallback, since sensors move little between eras) or when ``shot`` is
    None. Tolerates a legacy flat record (returned as-is)."""
    segs = rec.get("segments") if isinstance(rec, dict) else None
    if not segs:
        return rec  # legacy flat record → fields live at the top level
    segs = sorted(segs, key=lambda s: s.get("since_shot", 0))
    active = segs[0]
    for s in segs:
        if shot is not None and s.get("since_shot", 0) <= shot:
            active = s
    return active


def _device_slug(device):
    """JSON filename for ``device`` (e.g. ``'DIII-D'`` -> ``'diiid.json'``)."""
    if device in _DEVICE_FILE:
        return _DEVICE_FILE[device]
    return re.sub(r"[^a-z0-9]", "", str(device).lower()) + ".json"


def device_file(device="DIII-D"):
    """Path to the canonical device JSON for ``device``."""
    return os.path.join(DEVICE_DIR, _device_slug(device))


def load_device(device="DIII-D"):
    """Load (and cache) the device description JSON for ``device``.

    Returns the parsed dict: ``name, R0, wall{r,z}, sensors{...}, sensor_sets{...}``.
    """
    path = device_file(device)
    if path not in _device_cache:
        with open(path) as fh:
            _device_cache[path] = json.load(fh)
    return _device_cache[path]


def _norm_name(name):
    """Normalise a subset name so ``'Bp_LFS_midplane'`` == ``'Bp LFS midplane'``."""
    return str(name).strip().replace("_", " ")


def resolve_sensor_set(name, sets, _seen=None):
    """Flatten one ``sensor_sets`` entry to an ordered, de-duplicated name list.

    ``list`` sets return their ``sensors``; ``composite`` sets recurse into their
    member ``sets``.  Cycles are guarded against.
    """
    if _seen is None:
        _seen = set()
    if name in _seen or name not in sets:
        return []
    _seen.add(name)
    spec = sets[name]
    if spec.get("type") == "list":
        members = list(spec.get("sensors", []))
    else:  # composite
        members = []
        for sub in spec.get("sets", []):
            members += resolve_sensor_set(sub, sets, _seen)
    out, seen = [], set()
    for m in members:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def list_sensor_subsets(device="DIII-D"):
    """All named sensor subsets -> ``{name: [sensor, ...]}`` (composites flattened).

    This is the discoverability entry point: every key here is a valid
    ``channel_filter`` argument (with or without underscores).
    """
    sets = load_device(device).get("sensor_sets", {})
    return {name: resolve_sensor_set(name, sets) for name in sets}


def resolve_channel_filter(channel_filter, device="DIII-D"):
    """Map a friendly subset name (e.g. ``'Bp_LFS_midplane'``, ``'All_3D_Coils'``) to a pattern list.

    A known subset name resolves to the explicit (anchored) sensor names from the
    device ``sensor_sets``; an unknown string is treated as a raw regex and passed
    through.  Lists/tuples expand each element the same way.  Patterns are matched
    downstream with :func:`re.match`, so resolved names are anchored with ``$`` to
    avoid accidental prefix matches (e.g. ``C19`` vs ``C190``).
    """
    sets = load_device(device).get("sensor_sets", {})
    lookup = {_norm_name(k): k for k in sets}

    def resolve_one(cf):
        if isinstance(cf, str):
            key = lookup.get(_norm_name(cf))
            if key is not None:
                return [re.escape(s) + "$" for s in resolve_sensor_set(key, sets)]
            return [cf]  # raw regex
        return [cf]

    if isinstance(channel_filter, str):
        return resolve_one(channel_filter)
    out = []
    for cf in channel_filter:
        out += resolve_one(cf)
    return out


def sensor_geometry(device="DIII-D", shot=None):
    """Per-sensor geometry as an ``xarray.Dataset`` indexed by ``channel``.

    Carries the base fields from the device JSON (``r, z, phi, tilt, length,
    delta_phi, na``, plus ``pair``) **and** the derived poloidal angle ``theta``
    and sensor-end coordinates ``{r,z,phi,theta}_end1/2`` — the port of OMFIT's
    ``init_magnetics.py`` step.  A sensor is modelled as a straight segment of
    physical ``length`` centred at ``(r, z)`` and tilted by ``tilt`` (degrees) in
    the poloidal plane, spanning ``delta_phi`` (degrees) toroidally; angles are
    measured about the magnetic axis at ``(R0, 0)``.
    """
    import numpy as np
    import xarray as xr

    dev = load_device(device)
    R0 = float(dev["R0"])
    sensors = dev["sensors"]
    channels = list(sensors)

    # Each sensor is shot-segmented; resolve the segment active at `shot` before
    # reading its geometry (the flat `sensors[c]["r"]` lookup returns NaN now that
    # the fields live under `segments`).
    recs = {c: _segment_fields(sensors[c], shot) for c in channels}
    base = ["r", "z", "phi", "tilt", "length", "delta_phi", "na"]
    cols = {k: np.array([_to_float(recs[c].get(k, np.nan)) for c in channels]) for k in base}
    pairs = np.array([recs[c].get("pair", "None") for c in channels], dtype=object)

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


def load_sensor_table(device="DIII-D"):
    """Master sensor geometry (base + derived) — alias of :func:`sensor_geometry`."""
    return sensor_geometry(device)


def load_wall(device="DIII-D"):
    """Return the ``(r, z)`` first-wall outline arrays from the device JSON.

    Returns ``(None, None)`` if no device file or wall section is found.
    """
    try:
        dev = load_device(device)
    except (FileNotFoundError, OSError):
        return None, None
    wall = dev.get("wall")
    if not wall or "r" not in wall or "z" not in wall:
        return None, None
    return np.array(wall["r"], dtype=float), np.array(wall["z"], dtype=float)
