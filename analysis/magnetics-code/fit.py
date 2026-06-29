"""Port of ``SCRIPTS/fit_magnetics.py`` — the SLCONTOUR-style spatial fit.

This is the heart of the quasi-stationary analysis (VISION.md S4.1).  At each
time slice it fits the spatial field pattern with a cylindrical-Fourier basis

    dB(phi, theta) = Sum_nm  b_nm exp(i (n phi - m theta))

by SVD-conditioned least squares.  The design matrix ``A`` holds each basis
function evaluated at every sensor (finite-extent sensors get the analytic
"integral" averaging factor).  The fit reports the **condition number K** of
``A`` (the central trust metric — warn K>10, error K>20), per-coefficient error
bars, and reduced chi-squared.

Only the ``sinusoidal-point`` / ``sinusoidal-integral`` bases and the
``cylindrical`` / ``vertical`` geometries are ported (the Gaussian-RBF and
spherical paths from OMFIT are omitted as out of scope here).
"""

from __future__ import annotations

import re

import numpy as np
import xarray as xr

from omfit_compat import OMFITexception, delta_degrees, is_device, printe, printv, printw


def form_basis_function(n, m, x1, x2, y1, y2, fit_basis="sinusoidal-integral"):
    """Basis-function vector (one value per sensor) for toroidal/poloidal (n, m).

    ``x`` is the toroidal coordinate (phi), ``y`` the poloidal one (theta or z);
    ``*1``/``*2`` are the sensor extents in **degrees**.  Direct port of the
    OMFIT helper of the same name.
    """
    dx = delta_degrees(x1, x2)
    dy = delta_degrees(y1, y2)

    if fit_basis == "sinusoidal-point":
        # sinusoid evaluated at the sensor centre
        if n == 0:
            if m == 0:
                return np.ones_like(dx, dtype=complex)
            return np.exp(1j * m * np.deg2rad(y1 + dy / 2.0))
        if m == 0:
            return np.exp(1j * n * np.deg2rad(x1 + dx / 2.0))
        return np.exp(1j * m * np.deg2rad(y1 + dy / 2.0) + 1j * n * np.deg2rad(x1 + dx / 2.0))

    if fit_basis == "sinusoidal-integral":
        # sinusoid averaged across the sensor's (theta, phi) extent
        if n == 0:
            if m == 0:
                return np.ones_like(dx, dtype=complex)
            return (np.exp(1j * m * np.deg2rad(y2)) - np.exp(1j * m * np.deg2rad(y1))) / (
                np.deg2rad(dy) * 1j * m
            )
        if m == 0:
            return (np.exp(1j * n * np.deg2rad(x2)) - np.exp(1j * n * np.deg2rad(x1))) / (
                np.deg2rad(dx) * 1j * n
            )
        return (
            (np.exp(1j * m * np.deg2rad(y2)) - np.exp(1j * m * np.deg2rad(y1)))
            * (np.exp(1j * n * np.deg2rad(x2)) - np.exp(1j * n * np.deg2rad(x1)))
        ) / (np.deg2rad(dx * dy) * n * m)

    raise OMFITexception("Only 'sinusoidal-point' and 'sinusoidal-integral' bases are supported here.")


def fit(
    prepared,
    ns=(1, 2, 3),
    ms=(0,),
    channel_filter=".*",
    fit_exclude=(),
    fit_basis="sinusoidal-integral",
    fit_geometry="cylindrical",
    fit_cond=10.0,
    verbose=True,
):
    """Least-squares modal fit of the prepared data.

    :param prepared: PREPARED Dataset from :func:`prep.prepare`.
    :param ns: toroidal mode numbers in the basis.
    :param ms: poloidal mode numbers in the basis.
    :param channel_filter: restrict to channels matching this regex/list.
    :param fit_exclude: regexes excluding channels.
    :param fit_basis: 'sinusoidal-point' or 'sinusoidal-integral'.
    :param fit_geometry: 'cylindrical' (phi, theta) or 'vertical' (phi, z).
    :param fit_cond: condition-number cutoff for the lstsq inversion (= 1/rcond).
    :param verbose: print progress.
    :return: FIT Dataset (mirrors OMFIT ``OUTPUTS/FIT[key]``).
    """

    def _printv(*a):
        if verbose:
            printv(*a)

    _printv("Fitting the prepared data")

    # pick channels
    patterns = np.atleast_1d(channel_filter)
    excludes = np.atleast_1d(fit_exclude)
    channels = []
    for c in prepared["channel"].values:
        if any(re.match(p, c) for p in patterns) and not any(re.match(e, c) for e in excludes):
            if not np.all(np.isnan(prepared["signal"].sel(channel=c).values)):
                channels.append(c)
    if not channels:
        raise ValueError(f"No valid channels match {channel_filter!r}")

    ds = prepared.sel(channel=channels).copy()
    time = ds["time"].values
    helicity = int(ds.attrs.get("helicity", -1))

    # coordinate keys
    if fit_geometry == "cylindrical":
        xkey, ykey = "phi", "theta"
    elif fit_geometry == "vertical":
        xkey, ykey = "phi", "z"
    else:
        raise OMFITexception("fit_geometry must be 'cylindrical' or 'vertical' here.")

    x1 = ds[f"{xkey}_end1"].values
    x2 = ds[f"{xkey}_end2"].values
    y1 = ds[f"{ykey}_end1"].values
    y2 = ds[f"{ykey}_end2"].values

    sigma = ds["signal_sigma"].values.astype(float)
    bad = ~np.isfinite(sigma)
    if bad.any():
        fill = ds.attrs.get("sigma_type", np.nan)
        if not np.isfinite(fill):
            fill = np.nanmean(sigma) if np.isfinite(np.nanmean(sigma)) else 1.0
        sigma[bad] = fill

    # mode list, with helicity sign convention and (0,0) forced first
    ms = np.atleast_1d(ms)
    ns = np.atleast_1d(ns)
    dp = None  # paired (differential) sensors not present in this dataset
    if dp is None and 0 not in ns:
        _printv("WARNING: Sensors are not paired! Consider including n=0.")
    if not np.all(ms == 0) and not np.any(np.sign(ms) == helicity):
        ms = ms * -1
        _printv(f"WARNING: Flipping sign of m to conform to helicity {helicity:+}")
    nms = [(n, m) for m in ms for n in ns]
    if (0, 0) in nms:
        nms.insert(0, nms.pop(nms.index((0, 0))))
    nms_arr = np.array(nms)

    if is_device(ds.attrs.get("device", ""), "DIII-D"):
        if any(re.match(k, c) for k in ("C.*", "IL.*", "IU.*") for c in channels):
            if fit_basis != "sinusoidal-point":
                printe("WARNING: sinusoidal-point basis is used by DIII-D 3D coil operators")

    # --- build the design (basis) matrix A -------------------------------- #
    A_cols = []
    ncomp = []  # 1 (real-only) or 2 (real+imag) columns per mode
    for n, m in nms:
        fmn = form_basis_function(n, m, x1, x2, y1, y2, fit_basis) / sigma
        if np.allclose(fmn.imag, 0):
            A_cols.append(fmn.real)
            ncomp.append(1)
        else:
            A_cols.append(fmn.real)
            A_cols.append(fmn.imag)
            ncomp.append(2)
            # guard against aliasing from equally-spaced probes
            try:
                wtest = np.linalg.svd(np.array(A_cols).T, compute_uv=False)
                if np.abs(wtest[0] / wtest[-1]) > 1e19:
                    raise ValueError("Bad sensor distribution")
            except (ValueError, np.linalg.LinAlgError):
                printe(f" - Ill-conditioned mode ({n},{m}); fitting single component")
                x0 = x1[0] + delta_degrees(x1[0], x2[0]) / 2.0
                y0 = y1[0] + delta_degrees(y1[0], y2[0]) / 2.0
                fmn = form_basis_function(n, m, x1 + x0, x2 + x0, y1 + y0, y2 + y0, fit_basis) / sigma
                A_cols = A_cols[:-2] + [fmn.real]
                ncomp[-1] = 1

    A = np.array(A_cols).T  # (n_sensors, n_columns)
    if A.shape[1] > A.shape[0]:
        printw(f"Fitting {A.shape[1]} basis functions with {A.shape[0]} sensors")

    # --- SVD of A (condition number + per-coefficient error) -------------- #
    U_a, w_a, Vh_a = np.linalg.svd(A)
    c_a = np.abs(w_a[0] / w_a)
    valid = c_a <= fit_cond
    raw_cn = float(np.abs(w_a[0] / w_a[-1]))
    eff_cn = float(np.max(c_a[valid]))

    # --- least-squares fit at every time slice ---------------------------- #
    _printv(" - Fitting signal")
    b = (ds["signal"] / xr.DataArray(sigma, coords={"channel": ds["channel"]}, dims=("channel",))).values
    x, residual, rank_fit, s_a = np.linalg.lstsq(A, b, rcond=1.0 / fit_cond)
    _printv(f" - Raw / effective condition number = {raw_cn:.3g} / {eff_cn:.3g}")
    fit_coeffs = np.asarray(x)  # (n_columns, n_time)

    # per-coefficient sigma from the pseudo-inverse singular values
    w_inv = 1.0 / w_a
    w_inv[~valid] = 0.0
    w_inv = np.hstack((w_inv, [0.0] * max(Vh_a.shape[0] - w_a.shape[0], 0)))
    fit_sigma2 = np.sum((Vh_a.T * w_inv) ** 2, axis=0)
    fit_sigmas = np.sqrt(fit_sigma2)  # (n_columns,)

    # --- reform complex coefficients per mode ----------------------------- #
    coeffs_c, sigmas_c = [], []
    j = 0
    for nc in ncomp:
        if nc == 1:
            coeffs_c.append(fit_coeffs[j] + 0j)
            sigmas_c.append(fit_sigmas[j] + 0j)
        else:
            coeffs_c.append(fit_coeffs[j] + 1j * fit_coeffs[j + 1])
            sigmas_c.append(fit_sigmas[j] + 1j * fit_sigmas[j + 1])
        j += nc
    coeffs_c = np.array(coeffs_c)  # (n_modes, n_time)
    sigmas_c = np.array(sigmas_c)[:, None] * np.ones_like(time)  # (n_modes, n_time)

    # reconstructed signal, residual, chi-squared
    fit_b = np.dot(A, fit_coeffs).real.reshape(ds["channel"].shape[0], -1)
    ds["fit_signal"] = xr.DataArray(fit_b, coords=ds["signal"].coords, dims=ds["signal"].dims) * ds[
        "signal_sigma"
    ].fillna(float(sigma.mean()))
    ds["fit_ns"] = xr.DataArray(nms_arr[:, 0], coords={"mode": np.arange(len(nms))}, dims=("mode",))
    ds["fit_ms"] = xr.DataArray(nms_arr[:, 1], coords={"mode": np.arange(len(nms))}, dims=("mode",))
    ds["fit_coeffs"] = xr.DataArray(
        coeffs_c, coords={"mode": np.arange(len(nms)), "time": ds["time"]}, dims=("mode", "time")
    )
    ds["fit_sigmas"] = xr.DataArray(
        sigmas_c, coords={"mode": np.arange(len(nms)), "time": ds["time"]}, dims=("mode", "time")
    )

    ds["residual"] = ds["signal"] - ds["fit_signal"]
    sig_for_chi = xr.DataArray(sigma, coords={"channel": ds["channel"]}, dims=("channel",))
    ds["chi_sq"] = ((ds["residual"] / sig_for_chi) ** 2).sum("channel")
    nu = max(b.shape[0] - rank_fit, 1)
    ds["red_chi_sq"] = ds["chi_sq"] / nu

    ds["basis"] = xr.DataArray(
        A,
        coords={"basis_channel": np.arange(A.shape[0]), "basis_mode": np.arange(A.shape[1])},
        dims=("basis_channel", "basis_mode"),
    )

    _printv(f" - Mean reduced chi squared = {np.nanmean(ds['red_chi_sq'].values):.3e}")

    # metadata needed by the plots / reconstruction
    ds.attrs.update(
        fit_basis=fit_basis,
        fit_geometry=fit_geometry,
        fit_condition=fit_cond,
        raw_cn=raw_cn,
        eff_cn=eff_cn,
        condition_number=raw_cn,  # the VISION "K"
        fit_ncycle=0,
        fit_mcycle=0,
        fit_neps=np.inf,
        fit_meps=np.inf,
    )
    _condition_warning(raw_cn)
    return ds


def _condition_warning(K):
    """SLCONTOUR's K-thresholds (VISION S4.1): warn > 10, error > 20."""
    if K > 20:
        printe(f"Condition number K = {K:.1f} > 20: fit is untrustworthy (under-resolved array).")
    elif K > 10:
        printw(f"Condition number K = {K:.1f} > 10: fit may be poorly resolved.")
