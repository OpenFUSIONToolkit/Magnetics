"""Port of ``SCRIPTS/run_magnetics.py`` — the load -> prep -> fit orchestrator.

OMFIT's ``run_steps`` loops over channel filters, running fetch/prep/fit for
each and (optionally) plotting the mode dynamics.  Locally "fetch" is just the
loader, so this orchestrates load -> prep -> fit and returns all the
intermediate Datasets bundled in a :class:`MagneticsRun` for the caller (e.g.
the example notebook) to plot.
"""

from __future__ import annotations

from dataclasses import dataclass

import xarray as xr

from . import fit as _fit
from . import prep as _prep
from .io_data import ShotData, load_shot


@dataclass
class MagneticsRun:
    """Results of one load -> prep -> fit pass."""

    shotdata: ShotData
    prepared: xr.Dataset
    plasma: xr.Dataset
    fit: xr.Dataset

    @property
    def raw(self):
        return self.shotdata.raw

    @property
    def shot(self):
        return self.shotdata.shot

    @property
    def device(self):
        return self.shotdata.device

    @property
    def condition_number(self):
        """The fit's design-matrix condition number K (VISION's trust metric)."""
        return float(self.fit.attrs["condition_number"])


def run_steps(
    shot,
    channel_filter="Bp_LFS_midplane",
    ns=(1, 2, 3),
    ms=(0,),
    time_trim=(3.3, 3.5),
    prep_kwargs=None,
    fit_kwargs=None,
    data_root=None,
    verbose=True,
):
    """Run load -> prep -> fit for one shot and one channel filter.

    :param shot: shot number or a path to a ``shot_<n>.h5`` file.
    :param channel_filter: regex/list or a friendly name from the device file's
        ``sensor_sets`` (default ``'Bp_LFS_midplane'`` -> the LFS midplane
        toroidal Bp array).
    :param ns, ms: toroidal / poloidal mode numbers for the fit basis.
    :param time_trim: (t1, t2) seconds analysis window (must fall inside the
        shot file's window — e.g. shot 199749 spans 3.3-3.5 s).
    :param prep_kwargs: extra keyword args for :func:`prep.prepare`.
    :param fit_kwargs: extra keyword args for :func:`fit.fit`.
    :param data_root: override the ``data/datafile`` root directory.
    :param verbose: print progress.
    :return: :class:`MagneticsRun`.
    """
    prep_kwargs = dict(prep_kwargs or {})
    fit_kwargs = dict(fit_kwargs or {})

    sd = load_shot(shot, **({"data_root": data_root} if data_root else {}))

    prepared, plasma = _prep.prepare(
        sd,
        channel_filter=channel_filter,
        time_trim=time_trim,
        verbose=verbose,
        **prep_kwargs,
    )

    # Restrict the fit to the same channels prep selected, then fit the modes.
    fitds = _fit.fit(
        prepared,
        ns=ns,
        ms=ms,
        verbose=verbose,
        **fit_kwargs,
    )

    return MagneticsRun(shotdata=sd, prepared=prepared, plasma=plasma, fit=fitds)
