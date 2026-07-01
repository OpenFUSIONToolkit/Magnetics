"""Ports of the relevant ``PLOTS/*`` scripts (the SLCONTOUR / locked-mode set).

Each function takes the Datasets produced by :mod:`prep` / :mod:`fit` and an
optional axis, replacing the OMFIT runtime helpers (``cornernote``, ``uband``,
``View1d`` ...) with the local shim in :mod:`omfit_compat`.

Covered (per VISION.md S4.1 outputs):
  * :func:`plot_sensors`   - sensor map (R-Z / unrolled phi-theta)
  * :func:`plot_signal`    - RAW vs PREPARED time traces
  * :func:`plot_fit`       - reduced chi^2 / signals / worst residuals
  * :func:`plot_fit_modes` - amplitude & phase of each (m/n) mode vs time
  * :func:`plot_slice`     - the classic SLCONTOUR phi-vs-time contour
  * :func:`plot_svds`      - data-matrix SVD energy & design-matrix conditioning
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np

from .omfit_compat import cornernote, load_wall, printe, uband


# --------------------------------------------------------------------------- #
# Sensor map  (<- plot_magnetics_sensors.py)
# --------------------------------------------------------------------------- #
def _no_wrap(a):
    """Avoid mis-plotting sensors that straddle an angle wrap."""
    x = np.atleast_1d(np.array(a, dtype=float))
    if np.ptp(x) > 240:
        x[x == x.min()] += 360
    return x


def plot_sensors(raw, channel_filter=".*", geometry="rz", ax=None, device=None, **plot_kwargs):
    """Plot sensor locations for channels matching ``channel_filter``.

    :param geometry: 'rz' (cross-section), 'flat' (phi, z) or 'cylindrical'
        (phi, theta).
    """
    if ax is None:
        _, ax = plt.subplots(1, 1)
    device = device or str(raw.attrs.get("device", "DIII-D"))

    channels = [c for c in raw["channel"].values if re.match(channel_filter, c)]

    line = None
    for c in channels:
        s = raw.sel(channel=c)
        if geometry == "rz":
            x = [float(s["r_end1"]), float(s["r_end2"])]
            y = [float(s["z_end1"]), float(s["z_end2"])]
        elif geometry == "flat":
            x = [float(s["phi_end1"]), float(s["phi_end2"]), float(s["phi_end2"]), float(s["phi_end1"]), float(s["phi_end1"])]
            y = [float(s["z_end1"]), float(s["z_end1"]), float(s["z_end2"]), float(s["z_end2"]), float(s["z_end1"])]
        else:  # cylindrical
            x = _no_wrap([float(s["phi_end1"]), float(s["phi_end2"]), float(s["phi_end2"]), float(s["phi_end1"]), float(s["phi_end1"])])
            y = _no_wrap([float(s["theta_end1"]), float(s["theta_end1"]), float(s["theta_end2"]), float(s["theta_end2"]), float(s["theta_end1"])])
        if line is not None:
            plot_kwargs["color"] = line.get_color()
        (line,) = ax.plot(x, y, label=c, **plot_kwargs)

    if geometry == "rz":
        r_wall, z_wall = load_wall(device)
        if r_wall is not None:
            ax.plot(r_wall, z_wall, color="0.4", lw=1, label="wall")
        ax.set_xlabel("R (m)")
        ax.set_ylabel("z (m)")
        ax.set_aspect("equal")
    elif geometry == "flat":
        ax.set_xlabel("phi (deg)")
        ax.set_ylabel("z (m)")
    else:
        ax.set_xlabel("phi (deg)")
        ax.set_ylabel("theta (deg)")
        ax.set_xlim(0, 360)
        ax.set_ylim(-180, 180)

    cornernote(ax=ax, device=device, shot=raw.attrs.get("shot", ""))
    return ax


# --------------------------------------------------------------------------- #
# Time traces  (<- plot_magnetics_signal.py, '1d' style)
# --------------------------------------------------------------------------- #
def plot_signal(raw, prepared, channel_filter=".*", ax=None, legend_maxnum=12):
    """Overplot PREPARED traces with the (shifted) RAW traces for comparison."""
    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(8, 4))

    channels = [c for c in prepared["channel"].values if re.match(channel_filter, c)]
    ptps, lines = [], []
    for c in channels:
        s = prepared["signal"].sel(channel=c)
        s_ptp = np.ptp(np.nan_to_num(s.values))
        if s_ptp <= 0:
            printe(f"{c} has no signal")
            continue
        # the raw trace, shifted to match the prepared trace at t0 (shows filtering)
        s2 = raw["signal"].sel(channel=c, time=s["time"])
        s2 = s2 - (float(s2.values[0]) - float(s.values[0]))
        (l2,) = ax.plot(s2["time"], s2.values, alpha=0.4)
        (l,) = ax.plot(s["time"], s.values, color=l2.get_color(), label=c)
        lines.append(l)
        ptps.append(s_ptp)

    if ptps:
        ptps, lines = zip(*sorted(zip(ptps, lines), key=lambda z: z[0]))
        nleg = min(legend_maxnum, len(lines))
        for l in lines[:-nleg] if nleg < len(lines) else []:
            l.set_color("grey")
            l.set_alpha(0.4)
        ax.legend([l for l in lines[-nleg:]], [l.get_label() for l in lines[-nleg:]], loc=2, frameon=False, fontsize=8)

    ax.set_xlabel("time (s)")
    ax.set_ylabel("signal")
    ax.set_title("RAW (faint) vs PREPARED")
    cornernote(ax=ax, device=prepared.attrs.get("device", ""), shot=prepared.attrs.get("shot", ""))
    return ax


# --------------------------------------------------------------------------- #
# Fit quality  (<- plot_magnetics_fit.py)
# --------------------------------------------------------------------------- #
def plot_fit(fit, axes=None, legend_maxnum=6):
    """3-panel fit-quality overview: reduced chi^2, signals, worst residuals."""
    if axes is None:
        _, axes = plt.subplots(3, sharex=True, figsize=(8, 9))

    fit["red_chi_sq"].plot(ax=axes[0])
    axes[0].axhline(1, color="k", lw=0.5)
    axes[0].set_ylabel(r"Reduced $\chi^2$")
    axes[0].set_yscale("log")
    axes[0].set_ylim(1e-2, 1e3)

    res_ptp = []
    for c in fit["channel"].values:
        fit["signal"].sel(channel=c).plot(ax=axes[1], label=c)
        fit["residual"].sel(channel=c).plot(ax=axes[2], label=c)
        res_ptp.append(np.ptp(fit["residual"].sel(channel=c).values))
    axes[1].set_ylabel("Signal")
    axes[2].set_ylabel("Residual")

    # legend only the worst residual channels
    order = np.argsort(res_ptp)[::-1][:legend_maxnum]
    handles = [axes[2].lines[i] for i in sorted(order)]
    axes[2].legend(handles, [h.get_label() for h in handles], loc=2, frameon=False, fontsize=8)
    for ax in axes:
        ax.set_title("")
    axes[2].set_ylim(*axes[1].get_ylim())
    axes[0].set_title(str(fit.attrs.get("shot", "")))
    axes[2].set_xlabel("time (s)")
    cornernote(ax=axes[2], device=fit.attrs.get("device", ""), shot=fit.attrs.get("shot", ""))
    return axes


# --------------------------------------------------------------------------- #
# Mode amplitude & phase vs time  (<- plot_magnetics_fit_modes.py)
# --------------------------------------------------------------------------- #
def _amp_phase_with_errors(coeff, sigma):
    """Amplitude/phase and their 1-sigma errors from complex coeff & sigma.

    ``sigma`` holds the std of the real & imaginary parts (sigma.real, sigma.imag).
    Replaces the OMFIT ``unumpy`` propagation.
    """
    c, s = coeff.real, coeff.imag
    ec, es = sigma.real, sigma.imag
    amp = np.sqrt(c**2 + s**2)
    denom = np.where(amp == 0, np.nan, amp)
    amp_err = np.sqrt((c * ec) ** 2 + (s * es) ** 2) / denom
    phase = np.rad2deg(np.arctan2(s, c))
    p2 = np.where((c**2 + s**2) == 0, np.nan, c**2 + s**2)
    phase_err = np.rad2deg(np.sqrt((c * es) ** 2 + (s * ec) ** 2) / p2)
    return amp, np.nan_to_num(amp_err), phase, np.nan_to_num(phase_err)


def plot_fit_modes(fit, axes=None, legend_maxnum=12):
    """Amplitude (top) and phase (bottom) of each (m/n) mode vs time.

    The central mode-dynamics view: a rotating mode shows a steadily winding
    phase; locking shows the phase flattening while amplitude grows.
    """
    if axes is None:
        _, axes = plt.subplots(2, sharex=True, figsize=(8, 8))

    t = fit["time"].values
    max_amp = np.max([np.percentile(np.abs(fit["fit_coeffs"]).sel(mode=m).values, 90) for m in fit["mode"].values])

    amps = []
    for i, m in enumerate(fit["mode"].values):
        coeff = fit["fit_coeffs"].sel(mode=m).values
        sigma = fit["fit_sigmas"].sel(mode=m).values
        nval = int(fit["fit_ns"].values[i])
        mval = int(fit["fit_ms"].values[i])
        label = f"{mval}/{nval}"
        amp, amp_err, phase, phase_err = _amp_phase_with_errors(coeff, sigma)
        (l,) = uband(t, amp, amp_err, ax=axes[0], label=label)
        amps.append(np.max(amp))
        # only draw phase for modes with appreciable amplitude (avoid clutter)
        if np.percentile(np.abs(coeff), 90) > 0.1 * max_amp:
            uband(t, phase, phase_err, ax=axes[1], label=label, color=l.get_color())

    # de-emphasise the smallest modes, then build a compact legend
    leg_title = "n" if np.all(fit["fit_ms"].values == 0) else "m/n"
    handles = axes[0].lines
    order = np.argsort(amps)[::-1][:legend_maxnum]
    leg_handles = [handles[i] for i in sorted(order)]
    axes[0].legend(
        leg_handles,
        [h.get_label() for h in leg_handles],
        loc=2,
        ncol=1 + (len(leg_handles) > 5),
        title=leg_title,
        frameon=False,
    )

    axes[0].set_title(str(fit.attrs.get("shot", "")))
    axes[0].set_ylabel("Amplitude")
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylabel("Phase (deg)")
    axes[1].set_xlabel("Time (s)")
    axes[1].set_ylim(-180, 180)
    axes[1].set_yticks([-180, -90, 0, 90, 180])
    cornernote(ax=axes[1], device=fit.attrs.get("device", ""), shot=fit.attrs.get("shot", ""))
    return axes


# --------------------------------------------------------------------------- #
# SLCONTOUR phi-vs-time contour  (<- plot_magnetics_slice.py)
# --------------------------------------------------------------------------- #
def plot_slice(fit, fix_coord="theta", fix_value=0.0, ngrid=120, ax=None, trace_peak=True, **plot_kwargs):
    """Reconstruct the fitted field on a (phi or theta) x time grid and contour it.

    This is the classic SLCONTOUR locked/slowly-rotating-mode picture: a rotating
    mode appears as diagonal stripes that straighten out (lock) as it slows.
    Only the sinusoidal bases / cylindrical & vertical geometries are supported.
    """
    geom = fit.attrs.get("fit_geometry", "cylindrical")
    ns = fit["fit_ns"]
    ms = fit["fit_ms"]

    # build the reconstruction grid (the swept coordinate) and the fixed one
    if geom == "cylindrical" and fix_coord == "theta":
        ygrid = np.deg2rad(fix_value)
        deg = np.linspace(0, 360, ngrid)
        xgrid = np.deg2rad(deg)
        swept, swept_label = deg, "Toroidal Angle (deg.)"
    elif geom == "cylindrical" and fix_coord == "phi":
        deg = np.linspace(-180, 180, ngrid)
        ygrid = np.deg2rad(deg)
        xgrid = np.deg2rad(fix_value)
        swept, swept_label = deg, "Poloidal Angle (deg.)"
    elif geom == "vertical" and fix_coord == "phi":
        zs = np.hstack((fit["z_end1"].values, fit["z_end2"].values))
        zbuf = 0.1 * np.ptp(zs)
        zgrid = np.linspace(zs.min() - zbuf, zs.max() + zbuf, ngrid)
        ygrid = zgrid
        xgrid = np.deg2rad(fix_value)
        swept, swept_label = zgrid, "z (m)"
    else:  # vertical / z
        ygrid = fix_value
        deg = np.linspace(0, 360, ngrid)
        xgrid = np.deg2rad(deg)
        swept, swept_label = deg, "Toroidal Angle (deg.)"

    # field(swept, time) = Re Sum_modes coeff(t) exp(-i (n*xgrid + m*ygrid))
    coeffs = fit["fit_coeffs"].values  # (mode, time)
    nvals = ns.values[:, None]
    mvals = ms.values[:, None]
    phase = np.exp(-1j * (nvals * np.atleast_1d(xgrid)[None, :] + mvals * np.atleast_1d(ygrid)[None, :]))
    # (swept, time): sum over modes of coeff(mode,time) * phase(mode,swept)
    field = np.real(np.einsum("ms,mt->st", phase, coeffs))  # (swept, time)

    t = fit["time"].values
    plot_kwargs.setdefault("cmap", "RdBu_r")
    vmax = np.nanpercentile(np.abs(field), 99)

    if trace_peak:
        from matplotlib.gridspec import GridSpec

        if ax is None:
            fig = plt.figure(figsize=(9, 6))
        else:
            fig = ax.get_figure()
        gs = GridSpec(4, 1, figure=fig, hspace=0.05)
        axx = fig.add_subplot(gs[0, 0])
        axm = fig.add_subplot(gs[1:, 0], sharex=axx)
    else:
        if ax is None:
            fig, axm = plt.subplots(figsize=(9, 5))
        else:
            fig, axm = ax.get_figure(), ax
        axx = None

    im = axm.pcolormesh(t, swept, field, vmin=-vmax, vmax=vmax, shading="auto", **plot_kwargs)
    cb = fig.colorbar(im, ax=axm, pad=0.02)
    cb.set_label("Fit")
    axm.set_xlabel("Time (s)")
    axm.set_ylabel(swept_label)

    # peak location + an upper amplitude (RMS over the swept coordinate) trace
    if "Toroidal" in swept_label:
        ipeak = np.argmax(field, axis=0)
        axm.plot(t, swept[ipeak], "o", color="w", mfc="none", ms=3)
        axm.set_yticks([0, 90, 180, 270, 360])
    if axx is not None:
        rms = np.sqrt(np.mean(field**2, axis=0))
        axx.plot(t, rms)
        axx.set_ylabel("RMS")
        plt.setp(axx.get_xticklabels(), visible=False)
        axx.set_title(str(fit.attrs.get("shot", "")))

    cornernote(ax=axm, device=fit.attrs.get("device", ""), shot=fit.attrs.get("shot", ""))
    return axm


# --------------------------------------------------------------------------- #
# SVD conditioning diagnostics  (<- plot_magnetics_svds.py)
# --------------------------------------------------------------------------- #
def plot_svds(fit, axes=None):
    """Data-matrix SVD cumulative energy (top) & design-matrix conditioning (bottom)."""
    if axes is None:
        _, axes = plt.subplots(2, figsize=(7, 8))

    # data-matrix SVD
    s = fit["signal_precon_svals"].values
    energy_frac = np.cumsum(s**2) / np.sum(s**2)
    idx = np.arange(len(s)) + 1
    rank = int(fit.attrs.get("signal_effective_rank", len(s)))
    axes[0].plot(idx, energy_frac, "o-", label="All")
    ignored = energy_frac.copy()
    ignored[:rank] = np.nan
    axes[0].plot(idx, ignored, "x", linestyle="", label="Removed")
    axes[0].axhline(fit.attrs.get("signal_energy_limit", 1.0), color="k", linestyle="--")
    axes[0].set_xlim(left=0)
    axes[0].set_xlabel("Cumulative Singular Value Index")
    axes[0].set_ylabel("Energy Fraction")
    axes[0].set_title("Data Matrix Conditioning")
    axes[0].legend()

    # design-matrix SVD
    A = fit["basis"].values
    w_a = np.linalg.svd(A, compute_uv=False)
    c_a = np.abs(w_a[0] / w_a)
    fit_cond = fit.attrs.get("fit_condition", np.inf)
    ignored_c = c_a.copy()
    ignored_c[c_a < fit_cond] = np.nan
    axes[1].plot(np.arange(len(c_a)) + 1, c_a, "o-", label="All")
    axes[1].plot(np.arange(len(c_a)) + 1, ignored_c, "x", linestyle="", label="Removed")
    axes[1].axhline(fit_cond, color="k", linestyle="--")
    axes[1].set_xlim(left=0)
    axes[1].set_xlabel("Singular Value Index")
    axes[1].set_ylabel("Condition Number")
    axes[1].set_title("Design Matrix Conditioning")
    axes[1].legend()

    fig = axes[0].get_figure()
    fig.tight_layout()
    return axes
