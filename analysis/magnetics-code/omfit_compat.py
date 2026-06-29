"""Compatibility shim for the OMFIT runtime symbols used by the magnetics scripts.

The OMFIT magnetics module (``analysis/OMFIT-magnetics/``) runs inside the OMFIT
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
# These live in the copied OMFIT module under DATA/<device>/.  We read them
# directly rather than duplicating them.

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
#: DATA root of the copied OMFIT magnetics module.
OMFIT_DATA_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "OMFIT-magnetics", "DATA"))


def device_data_dir(device):
    """Directory holding the reference tables for ``device`` (e.g. 'DIII-D')."""
    return os.path.join(OMFIT_DATA_DIR, str(device))


def _extract_quoted(s):
    """All single-quoted tokens on a line, in order."""
    return re.findall(r"'([^']*)'", s)


def load_channel_filters(device="DIII-D"):
    """Parse ``channel_filters.txt`` into ``{name: [regex, ...]}``.

    Handles the line-continuation used for multi-array filters (a wrapped line
    with no ``=`` continues the previous entry).
    """
    path = os.path.join(device_data_dir(device), "channel_filters.txt")
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


def resolve_channel_filter(channel_filter, device="DIII-D"):
    """Map a friendly filter name (e.g. ``'Bp_LFS_midplane'``) to its regex list.

    If ``channel_filter`` is already a regex (or list of regexes), it is returned
    unchanged as a list.
    """
    filters = load_channel_filters(device)
    if isinstance(channel_filter, str):
        if channel_filter in filters:
            return list(filters[channel_filter])
        return [channel_filter]
    # a list/tuple: expand any known names, pass through the rest
    out = []
    for cf in channel_filter:
        out += filters.get(cf, [cf])
    return out


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
