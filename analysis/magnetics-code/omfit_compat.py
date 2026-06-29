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
# Device reference data (sensor geometry tables / wall / channel filters)
# --------------------------------------------------------------------------- #
# These reference tables are bundled with this package under ./DATA/<device>/,
# so nothing here depends on any sibling directory at runtime.

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
#: Root of the bundled device reference tables (see DATA/README.md for provenance).
DATA_DIR = os.path.join(_THIS_DIR, "DATA")


def device_data_dir(device):
    """Directory holding the reference tables for ``device`` (e.g. 'DIII-D')."""
    return os.path.join(DATA_DIR, str(device))


def _extract_quoted(s):
    """All single-quoted tokens on a line, in order."""
    return re.findall(r"'([^']*)'", s)


def _load_named_filters(path):
    """Parse a ``name = 'regex' ['regex' ...]`` table into ``{name: [regex, ...]}``.

    Handles the line-continuation used for multi-array filters (a wrapped line
    with no ``=`` continues the previous entry).
    """
    out = {}
    last = None
    with open(path) as fh:
        for line in fh:
            if not line.strip():
                continue
            if "=" in line:
                name, rhs = line.split("=", 1)
                last = name.strip()
                out[last] = _extract_quoted(rhs)
            elif last is not None:
                out[last] += _extract_quoted(line)
    return out


def load_channel_filters(device="DIII-D"):
    """Named **sensor** subsets from ``channel_filters.txt`` -> ``{name: [regex, ...]}``."""
    return _load_named_filters(os.path.join(device_data_dir(device), "channel_filters.txt"))


def load_coil_filters(device="DIII-D"):
    """Named **3D-coil** subsets from ``coil_filters.txt`` -> ``{name: [regex, ...]}``."""
    return _load_named_filters(os.path.join(device_data_dir(device), "coil_filters.txt"))


def list_sensor_subsets(device="DIII-D"):
    """All named sensor + coil subsets, merged -> ``{name: [regex, ...]}``.

    This is the discoverability entry point: every key here is a valid
    ``channel_filter`` argument.
    """
    subsets = load_channel_filters(device)
    subsets.update(load_coil_filters(device))
    return subsets


def resolve_channel_filter(channel_filter, device="DIII-D"):
    """Map a friendly subset name (e.g. ``'Bp_LFS_midplane'``, ``'3D_coils'``) to its regex list.

    Consults both the sensor and coil subset tables.  If ``channel_filter`` is
    already a regex (or list of regexes), it is returned unchanged as a list.
    """
    filters = list_sensor_subsets(device)
    if isinstance(channel_filter, str):
        if channel_filter in filters:
            return list(filters[channel_filter])
        return [channel_filter]
    # a list/tuple: expand any known names, pass through the rest
    out = []
    for cf in channel_filter:
        out += filters.get(cf, [cf])
    return out


def load_channel_alternates(device="DIII-D"):
    """new -> old PTDATA channel-name map from ``channel_alternates.txt``.

    Used in OMFIT as an MDSplus name fallback; unused locally but kept for
    posterity / reference.
    """
    path = os.path.join(device_data_dir(device), "channel_alternates.txt")
    out = {}
    with open(path) as fh:
        for line in fh:
            if "=" not in line:
                continue
            name, rhs = line.split("=", 1)
            quoted = _extract_quoted(rhs)
            if quoted:
                out[name.strip()] = quoted[0]
    return out


def load_sensor_table(device="DIII-D"):
    """Master sensor geometry table (``diiid_sensors.txt``) as an ``xarray.Dataset``.

    Columns: ``r, z, phi, tilt, length, delta_phi, na, pair`` indexed by
    ``channel``.  This mirrors what ``init_magnetics.py`` starts from (minus the
    derived ``*_end1/2`` coordinates).

    Reference loader only — the local pipeline reads geometry from the RAW
    netCDF, not this table.  Deriving the ``*_end`` coordinates from this table
    (the ``init`` step) is future work, useful only if a shot file ever lacks
    geometry.
    """
    import numpy as np
    import xarray as xr

    path = os.path.join(device_data_dir(device), "diiid_sensors.txt")
    numeric = ["r", "z", "phi", "tilt", "length", "delta_phi", "na"]
    channels, rows, pairs = [], [], []
    with open(path) as fh:
        header = fh.readline().split()  # channel r z phi tilt length delta_phi na pair
        cols = header[1:]
        for line in fh:
            tok = line.split()
            if len(tok) < len(header):
                continue
            channels.append(tok[0])
            vals = dict(zip(cols, tok[1:]))
            rows.append([_to_float(vals[c]) for c in numeric])
            pairs.append(vals.get("pair", "None"))
    arr = np.array(rows, dtype=float)
    ds = xr.Dataset(
        {name: ("channel", arr[:, i]) for i, name in enumerate(numeric)},
        coords={"channel": channels},
    )
    ds["pair"] = ("channel", np.array(pairs, dtype=object))
    ds.attrs["device"] = device
    return ds


def load_bdot_table(device="DIII-D"):
    """Bdot sensor positions/sizes (``diiid_bdots.txt``) as a list of dicts.

    Tolerant best-effort parse: skips the 2 header lines, ignores the irregular
    ``id``/``d`` flag column, and returns one record per sensor with its name and
    the numeric ``R, Z, tor, tilt, L, W, NA`` it could read.  Reference only.
    """
    path = os.path.join(device_data_dir(device), "diiid_bdots.txt")
    fields = ["R", "Z", "tor", "tilt", "L", "W", "NA"]
    out = []
    with open(path) as fh:
        lines = fh.readlines()[2:]  # drop the 2 header rows
    for line in lines:
        tok = line.split()
        if not tok:
            continue
        name = tok[0]
        nums = [t for t in tok[1:] if _to_float(t) == _to_float(t) and _is_number(t)]
        rec = {"name": name}
        rec.update({f: _to_float(v) for f, v in zip(fields, nums)})
        out.append(rec)
    return out


def _to_float(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return float("nan")


def _is_number(s):
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _parse_namelist_array(text):
    """Parse a Fortran-namelist numeric array, honouring ``N*value`` repeats."""
    vals = []
    for tok in text.replace(",", " ").split():
        if tok in ("/", "&end", "&END"):
            break
        if "*" in tok:
            n, v = tok.split("*")
            try:
                vals += [float(v)] * int(n)
            except ValueError:
                break
        else:
            try:
                vals.append(float(tok))
            except ValueError:
                break
    return np.array(vals)


def load_wall(device="DIII-D"):
    """Return the (r, z) first-wall outline arrays from ``<device_lower>.txt``.

    Returns ``(None, None)`` if no wall file/namelist is found.
    """
    fname = {"DIII-D": "diiid.txt"}.get(device, str(device).lower().replace("-", "") + ".txt")
    path = os.path.join(device_data_dir(device), fname)
    if not os.path.exists(path):
        return None, None
    raw = open(path).read()
    if "&wall" not in raw:
        return None, None
    body = raw.split("&wall", 1)[1]
    try:
        rpart = body.split("r =", 1)[1].split("z =", 1)[0]
        zpart = body.split("z =", 1)[1]
    except IndexError:
        return None, None
    return _parse_namelist_array(rpart), _parse_namelist_array(zpart)
