"""Port of ``SCRIPTS/prep_magnetics.py`` — signal conditioning before the fit.

Steps (matching the OMFIT original):
  1. trim channels (by regex) and time to the window of interest;
  2. optional DC vacuum compensation using the COUPLING matrix;
  3. optional integration (bdot -> B);
  4. optional downsample + causal Gaussian band/high/low-pass filter;
  5. optional detrend (none / baseline / linear / endpoints);
  6. SVD conditioning of the channel x time data matrix, keeping the singular
     values up to a cumulative-energy threshold (drops incoherent noise).

The result is the PREPARED Dataset consumed by :mod:`fit`.

OMFIT injects a patched ``scipy.ndimage.gaussian_filter1d`` that accepts a
``causal=True`` flag (a one-sided kernel).  Stock scipy has no such flag, so we
implement the causal Gaussian filter here (:func:`causal_gaussian`).
"""

from __future__ import annotations

import re

import numpy as np
import xarray as xr
from scipy.integrate import cumulative_trapezoid

from omfit_compat import is_device, printe, printv, printw, resolve_channel_filter


def causal_gaussian(values, sigma, truncate=4.0):
    """One-sided (causal) Gaussian smoothing along a 1-D array.

    Output sample ``n`` is a Gaussian-weighted average of samples ``<= n`` only,
    so the filter introduces no acausal smearing (important for sharp bdot
    spikes — see the note in the OMFIT prep script).  Matches the intent of
    OMFIT's ``gaussian_filter1d(..., causal=True)``.
    """
    values = np.asarray(values, dtype=float)
    if not np.isfinite(sigma) or sigma <= 0:
        return values.copy()
    radius = int(truncate * sigma + 0.5)
    if radius < 1:
        return values.copy()
    k = np.exp(-0.5 * (np.arange(radius + 1) / sigma) ** 2)
    k /= k.sum()  # k[0] weights the current sample, k[radius] the oldest
    pad = np.concatenate([np.full(radius, values[0]), values])
    return np.convolve(pad, k, mode="valid")


def prepare(
    shotdata,
    channel_filter=".*",
    time_trim=(2.9, 3.0),
    cutoff_hz=(0.0, 400.0),
    detrend_type="none",
    detrend_band=(0.0, 10.0),
    energy=1.0,
    integrate=False,
    dc_comp=False,
    dc_comp_coils=(),
    verbose=True,
):
    """Prepare magnetics data for fitting.

    :param shotdata: :class:`io_data.ShotData`.
    :param channel_filter: regex / list / friendly filter name.
    :param time_trim: (t1, t2) seconds — analysis window.
    :param cutoff_hz: (f_low, f_high) bandpass corners; ``f_low==0`` -> lowpass,
        ``f_high>=Nyquist`` -> highpass.
    :param detrend_type: 'none' | 'baseline' | 'linear' | 'endpoints'.
    :param detrend_band: (t1, t2) sub-interval used to estimate the trend.
    :param energy: fraction of data-matrix SVD energy to keep (<1 removes noise).
    :param integrate: integrate signals in time (bdot -> B).
    :param dc_comp: subtract DC vacuum coupling using the COUPLING matrix.
    :param dc_comp_coils: coil-name regexes to compensate.
    :param verbose: print progress.
    :return: ``(prepared, plasma_trimmed)`` Datasets.
    """

    def _printv(*a):
        if verbose:
            printv(*a)

    raw = shotdata.raw
    plasma = shotdata.plasma
    device = shotdata.device
    patterns = resolve_channel_filter(channel_filter, device)

    _printv(" - Trimming channels and time")
    tpad = 0.0 if cutoff_hz[0] == 0 else 1.0 / cutoff_hz[0]  # padding for the highpass

    channels = []
    for c in raw["channel"].values:
        if any(re.match(p, c) for p in patterns):
            if not np.all(np.isnan(raw["signal"].sel(channel=c).values)):
                channels.append(c)
    if not channels:
        raise ValueError(f"No valid channels match {channel_filter!r}")

    tmask = (raw["time"] >= time_trim[0] - tpad) & (raw["time"] <= time_trim[1] + tpad)
    ds = raw.sel(channel=channels).isel(time=np.where(tmask.values)[0]).transpose("channel", "time")
    t = ds["time"].values

    # ----- DC vacuum compensation ----------------------------------------- #
    if dc_comp and shotdata.coupling is not None and "dc_coupling" in shotdata.coupling:
        _printv(" - DC compensation")
        coil_channels = []
        for cf in np.atleast_1d(dc_comp_coils):
            coil_channels += [c for c in raw["channel"].values if re.match(cf, c)]
        if coil_channels:
            coil = raw["signal"].isel(time=np.where(tmask.values)[0]).sel(channel=coil_channels)
            coil = coil.rename({"channel": "coil"})
            coup = (coil * shotdata.coupling["dc_coupling"]).sum(dim="coil")
            invalid = [c for c in ds["channel"].values if c not in coup["channel"].values]
            if not invalid:
                ds["vacuum"] = coup.sel(channel=ds["channel"])
                ds["signal"] = ds["signal"] - ds["vacuum"]
            else:
                printe(f"No DC coupling record for {invalid} -> skipping DC compensation")
        else:
            printw("dc_comp requested but no coil channels matched -> skipping")

    # ----- device-specific signal swap (2019 DIII-D wiring mix-up) --------- #
    if is_device(device, "DIII-D") and shotdata.shot > 177705:
        present = set(ds["channel"].values)
        if {"ESLD66M079", "ESLD66M319"} <= present:
            printw("Swapping ESLD66M319/ESLD66M079 for this shot (2019 wiring mix-up)")
            tmp = ds["signal"].copy(deep=True)
            ds["signal"].loc[{"channel": "ESLD66M079"}] = tmp.sel(channel="ESLD66M319").values
            ds["signal"].loc[{"channel": "ESLD66M319"}] = tmp.sel(channel="ESLD66M079").values

    # ----- trim auxiliary (plasma) signals to the same window -------------- #
    aux_time = plasma["time"] / 1.0e3  # PLASMA_PARAMS time is in ms
    amask = (aux_time >= time_trim[0]) & (aux_time <= time_trim[1])
    plasma_trim = plasma.isel(time=np.where(amask.values)[0])

    # ----- integrate bdot -> B -------------------------------------------- #
    if integrate:
        _printv(" - Integrating")
        dx = t[1] - t[0]
        ds["signal"].values = np.apply_along_axis(
            cumulative_trapezoid, 1, ds["signal"].values, dx=dx, initial=0
        )

    # ----- frequency filter (before detrending) --------------------------- #
    nyqst = 0.5 / (t[1] - t[0]) if len(t) > 1 else 1e99
    if cutoff_hz[0] > 0 or cutoff_hz[1] < nyqst:
        step = int(min(max(1, int(nyqst / cutoff_hz[1])), np.ceil(t.shape[0] / 3e2)))
        if step > 1:
            _printv(f" - Downsampling x{step}")
            ds = ds.sel(time=t[::step])
            t = ds["time"].values
        dt = t[1] - t[0]
        _printv(" - Filtering")
        if cutoff_hz[0] == 0:
            _printv("   > causal lowpass")
            sigma = 0.25 / (dt * cutoff_hz[1])
            filter_func = lambda v: causal_gaussian(v, sigma)
        elif cutoff_hz[1] >= nyqst:
            _printv("   > causal highpass")
            sigma = 0.25 / (dt * cutoff_hz[0])
            filter_func = lambda v: v - causal_gaussian(v, sigma)
        else:
            _printv("   > causal bandpass")
            sigma0 = 0.25 / (dt * cutoff_hz[0])
            sigma1 = 0.25 / (dt * cutoff_hz[1])

            def filter_func(v):
                v = causal_gaussian(v, sigma1)
                v = v - causal_gaussian(v, sigma0)
                return v

        ds["signal"].values = np.apply_along_axis(filter_func, 1, ds["signal"].values)

    # remove the highpass padding
    tsel = t[(t >= time_trim[0]) & (t <= time_trim[1])]
    if len(tsel) == 0:
        raise ValueError(
            f"time_trim={time_trim} left 0 samples after filter/downsample "
            f"(downsampled dt≈{t[1]-t[0]:.4g} s, {len(t)} samples spanned "
            f"{t[0]:.4g}–{t[-1]:.4g} s). Widen the window or reduce cutoff_hz[0]."
        )
    ds = ds.sel(time=tsel)

    # ----- detrend -------------------------------------------------------- #
    _detrend(ds, channels, detrend_type.lower(), detrend_band, _printv)

    # ----- SVD conditioning of the data matrix ---------------------------- #
    _svd_condition(ds, energy, _printv)

    # carry the metadata the fit and plots rely on
    ds.attrs["shot"] = shotdata.shot
    ds.attrs["device"] = device
    ds.attrs["helicity"] = int(np.atleast_1d(plasma.attrs.get("helicity", -1))[0])
    if "sigma_type" in raw.attrs:
        ds.attrs["sigma_type"] = float(np.atleast_1d(raw.attrs["sigma_type"])[0])

    return ds, plasma_trim


def _detrend(ds, channels, detrend_type, detrend_band, _printv):
    """In-place detrend of ds['signal'] (port of the OMFIT detrend block)."""
    if detrend_type == "none":
        return

    time = ds["time"].values
    if detrend_type in ("baseline", "linear"):
        band = np.atleast_2d(detrend_band)
        det_times = np.concatenate(
            [time[(time >= b[0]) & (time <= b[1])] for b in band]
        )
        in_band = np.isin(time, det_times)
        if detrend_type == "baseline":
            _printv(" - Removing baseline")
            for ch in range(len(channels)):
                ds["signal"].values[ch] -= np.mean(ds["signal"].values[ch, in_band])
        else:
            _printv(" - Removing linear trend")
            for ch in range(len(channels)):
                pfit = np.poly1d(np.polyfit(det_times, ds["signal"].values[ch, in_band], 1))
                ds["signal"].values[ch] -= pfit(time)

    elif detrend_type == "endpoints":
        _printv(" - Removing endpoint trend")
        band = np.atleast_1d(detrend_band)
        sel = (time >= band[0]) & (time <= band[-1])
        tb = time[sel]
        for ch in range(len(channels)):
            s = ds["signal"].values[ch, sel]
            valid = np.isfinite(s)
            if np.sum(valid) > 1:
                ends = np.array((0, -1))
                pfit = np.poly1d(np.polyfit(tb[valid][ends], s[valid][ends], 1))
                ds["signal"].values[ch] -= pfit(time)
    else:
        raise ValueError("detrend_type must be none, baseline, linear, or endpoints")


def _svd_condition(ds, energy, _printv):
    """SVD-condition the data matrix and (optionally) remove incoherent noise."""
    P = len(ds["channel"])
    T = len(ds["time"])
    _printv(" - Conditioning data matrix")
    try:
        if T > 10000:
            raise MemoryError
        U, s, Vh = np.linalg.svd(ds["signal"].values / np.sqrt(P * T), full_matrices=False)
    except MemoryError:
        step = max(2, int(np.ceil(T / 10000)))
        printw(f"Downsampling time x{step} for an informational SVD only")
        U, s, Vh = np.linalg.svd(ds["signal"].values[:, ::step] / np.sqrt(P * T), full_matrices=False)
        energy = 1.0  # shapes won't match for reforming the data

    energy_tot = np.sum(s**2)
    cut = P
    for sindx in range(1, len(s)):
        if np.sum(s[:sindx] ** 2) / energy_tot > energy:
            cut = sindx
            if sindx < len(s) - 1 and s[sindx + 1] ** 2 > 0.5 * s[sindx] ** 2:
                cut += 1  # keep (cos, sin) pairs together
            break

    nsv = U.shape[1]
    ds["signal_precon_u"] = xr.DataArray(
        U,
        coords={"signal_svd_index": np.arange(nsv), "channel": ds["channel"]},
        dims=("channel", "signal_svd_index"),
    )
    ds["signal_precon_svals"] = xr.DataArray(
        s, coords={"signal_svd_index": np.arange(nsv)}, dims=["signal_svd_index"]
    )
    ds.attrs["signal_energy_limit"] = energy
    ds.attrs["signal_effective_rank"] = cut
    _printv(f"   > SVD found {cut} coherent structures of interest")

    if energy < 1.0 and U.shape == (P, len(s)) and len(s) > 0:
        smat = np.zeros((len(s), len(s)))
        for i in range(min(cut, len(s))):
            smat[i, i] = s[i]
        ds["signal"].values = np.dot(U, np.dot(smat, Vh)) * np.sqrt(P * T)
