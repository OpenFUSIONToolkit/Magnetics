"""A port of the OMFIT magnetics *fit* script — the QS pipeline's fit step.

This is the heart of the quasi-stationary analysis (VISION.md S4.1).  At each
time slice it fits the spatial field pattern with either a cylindrical-Fourier
basis

    dB(phi, theta) = Sum_nm  b_nm exp(i (n phi - m theta))

or a Gaussian-RBF basis

    dB(phi, theta) = Sum_k  a_k G(phi - phi_k, theta - theta_k; eps_phi, eps_theta)

by SVD-conditioned least squares.  The design matrix ``A`` holds each basis
function evaluated at every sensor (finite-extent sensors get the analytic
"integral" averaging factor).  The fit reports the **condition number K** of
``A`` (the central trust metric — warn K>10, error K>20), per-coefficient error
bars, and reduced chi-squared.

Supported bases:
  * ``sinusoidal-point``    — Fourier exp(i(n*phi + m*theta)) at sensor centre
  * ``sinusoidal-integral`` — Fourier exp averaged over the sensor (phi,theta) area
  * ``gaussian-point``      — Gaussian RBF evaluated at sensor centre
  * ``gaussian-integral``   — Gaussian RBF integrated over the sensor area (using erf)

Supported geometries: ``cylindrical`` (phi, theta) and ``vertical`` (phi, z).
"""

from __future__ import annotations

import logging
import re

import numpy as np
import xarray as xr

from .qs_device import is_device

logger = logging.getLogger(__name__)


def _delta_degrees_scalar(theta1, theta2):
    """Angular width from theta1 to theta2 in degrees, wrapping once through 0."""
    dt = theta2 - theta1
    if dt > 180:
        dt -= 360
    if dt < -180:
        dt += 360
    return dt


#: Vectorised signed angular width in degrees (ported from omfit_compat.delta_degrees).
delta_degrees = np.vectorize(_delta_degrees_scalar)


def form_basis_function(
    n,
    m,
    x1,
    x2,
    y1,
    y2,
    fit_basis="sinusoidal-integral",
    ncycle=0,
    mcycle=0,
    nepsilon=np.inf,
    mepsilon=np.inf,
):
    """Basis-function vector (one value per sensor) for mode/centre (n, m).

    For sinusoidal bases ``n``/``m`` are toroidal/poloidal mode numbers and
    the return is complex.  For Gaussian bases ``n``/``m`` are the RBF centre
    positions in degrees and the return is real.

    ``x`` is the toroidal coordinate (phi), ``y`` the poloidal one (theta or z);
    ``*1``/``*2`` are the sensor extents in **degrees**.
    ``ncycle``/``mcycle`` are the number of periodic copies to sum for the
    Gaussian bases (0 = no wrapping); ``nepsilon``/``mepsilon`` are the RBF
    widths in degrees (``np.inf`` = uniform in that direction).
    """
    dx = delta_degrees(x1, x2)
    dy = delta_degrees(y1, y2)

    # ── sinusoidal-point ──────────────────────────────────────────────────────
    if fit_basis == "sinusoidal-point":
        if n == 0:
            if m == 0:
                return np.ones_like(dx, dtype=complex)
            return np.exp(1j * m * np.deg2rad(y1 + dy / 2.0))
        if m == 0:
            return np.exp(1j * n * np.deg2rad(x1 + dx / 2.0))
        return np.exp(1j * m * np.deg2rad(y1 + dy / 2.0) + 1j * n * np.deg2rad(x1 + dx / 2.0))

    # ── sinusoidal-integral ───────────────────────────────────────────────────
    if fit_basis == "sinusoidal-integral":
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

    # ── gaussian-point ────────────────────────────────────────────────────────
    if fit_basis == "gaussian-point":
        xc = x1 + dx / 2.0  # sensor phi centre
        yc = y1 + dy / 2.0  # sensor theta/z centre
        fmn = np.zeros(len(np.atleast_1d(x1)), dtype=float)
        for nc in range(-ncycle, ncycle + 1):
            for mc in range(-mcycle, mcycle + 1):
                xterm = (((n + nc * 360) - xc) / nepsilon) ** 2 if np.isfinite(nepsilon) else 0.0
                yterm = (((m + mc * 360) - yc) / mepsilon) ** 2 if np.isfinite(mepsilon) else 0.0
                fmn += np.exp(-(xterm + yterm))
        return fmn

    # ── gaussian-integral ─────────────────────────────────────────────────────
    if fit_basis == "gaussian-integral":
        from scipy.special import erf

        fmn = np.zeros(len(np.atleast_1d(x1)), dtype=float)
        for nc in range(-ncycle, ncycle + 1):
            for mc in range(-mcycle, mcycle + 1):
                cx = n + nc * 360  # phi centre (with periodic copy)
                cy = m + mc * 360  # theta/z centre

                if np.isfinite(nepsilon) and np.isfinite(mepsilon):
                    # 2D integral: product of the two 1-D erf integrals.
                    # OMFIT source had a `)(` typo here (function-call instead
                    # of multiplication); fixed to `*`.
                    fmn += (
                        0.25
                        * np.pi
                        * nepsilon
                        * mepsilon
                        * (erf((x2 - cx) / nepsilon) - erf((x1 - cx) / nepsilon))
                        * (erf((y2 - cy) / mepsilon) - erf((y1 - cy) / mepsilon))
                    )
                elif np.isfinite(nepsilon):
                    # mepsilon = inf: ridge function in phi, uniform in theta/z
                    fmn += (
                        0.5
                        * np.sqrt(np.pi)
                        * nepsilon
                        * (erf((x2 - cx) / nepsilon) - erf((x1 - cx) / nepsilon))
                    )
                else:
                    # nepsilon = inf: ridge function in theta/z, uniform in phi
                    fmn += (
                        0.5
                        * np.sqrt(np.pi)
                        * mepsilon
                        * (erf((y2 - cy) / mepsilon) - erf((y1 - cy) / mepsilon))
                    )
        return fmn

    raise ValueError(
        "fit_basis must be 'sinusoidal-point', 'sinusoidal-integral', "
        "'gaussian-point', or 'gaussian-integral'."
    )


def fit(
    prepared,
    ns=(1, 2, 3),
    ms=(0,),
    channel_filter=".*",
    fit_exclude=(),
    fit_basis="sinusoidal-integral",
    fit_geometry="cylindrical",
    fit_cond=10.0,
    ncenters=6,
    mcenters=1,
    nepsilon=None,
    mepsilon=None,
    verbose=True,
):
    """Least-squares modal fit of the prepared data.

    :param prepared: PREPARED Dataset from :func:`prep.prepare`.
    :param ns: sinusoidal — toroidal mode numbers; gaussian — ignored (centres
        are computed from sensor extent + ``ncenters``).
    :param ms: sinusoidal — poloidal mode numbers; gaussian — ignored.
    :param channel_filter: restrict to channels matching this regex/list.
    :param fit_exclude: regexes excluding channels.
    :param fit_basis: ``'sinusoidal-point'``, ``'sinusoidal-integral'``,
        ``'gaussian-point'``, or ``'gaussian-integral'``.
    :param fit_geometry: ``'cylindrical'`` (phi, theta) or ``'vertical'`` (phi, z).
    :param fit_cond: condition-number cutoff for the lstsq inversion (= 1/rcond).
    :param ncenters: **Gaussian only** — number of phi RBF centres.
    :param mcenters: **Gaussian only** — number of theta/z RBF centres.
    :param nepsilon: **Gaussian only** — phi RBF width in degrees; ``None`` =
        auto (mean spacing between centres).
    :param mepsilon: **Gaussian only** — theta/z RBF width in degrees; ``None``
        = auto (``np.inf`` when ``mcenters == 1``).
    :param verbose: print progress.
    :return: FIT Dataset (mirrors OMFIT ``OUTPUTS/FIT[key]``).
    """

    def _printv(*a):
        if verbose:
            logger.info(" ".join(str(x) for x in a))

    _printv("Fitting the prepared data")

    # ── channel selection ─────────────────────────────────────────────────────
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

    # ── coordinate keys ───────────────────────────────────────────────────────
    if fit_geometry == "cylindrical":
        xkey, ykey = "phi", "theta"
    elif fit_geometry == "vertical":
        xkey, ykey = "phi", "z"
    else:
        raise ValueError("fit_geometry must be 'cylindrical' or 'vertical'.")

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

    # ── basis-specific mode / centre setup ────────────────────────────────────
    is_sinusoidal = fit_basis.startswith("sinusoidal")
    is_gaussian = fit_basis.startswith("gaussian")

    if is_sinusoidal:
        ms = np.atleast_1d(ms)
        ns = np.atleast_1d(ns)
        dp = None  # paired sensors not present in this dataset
        if dp is None and 0 not in ns:
            _printv("WARNING: Sensors are not paired! Consider including n=0.")
        if not np.all(ms == 0) and not np.any(np.sign(ms) == helicity):
            ms = ms * -1
            _printv(f"WARNING: Flipping sign of m to conform to helicity {helicity:+}")
        nms = [(n, m) for m in ms for n in ns]
        if (0, 0) in nms:
            nms.insert(0, nms.pop(nms.index((0, 0))))
        nms_arr = np.array(nms)
        _ncycle = _mcycle = 0
        _nepsilon = _mepsilon = np.inf

        if is_device(ds.attrs.get("device", ""), "DIII-D"):
            if any(re.match(k, c) for k in ("C.*", "IL.*", "IU.*") for c in channels):
                if fit_basis != "sinusoidal-point":
                    logger.warning("sinusoidal-point basis is used by DIII-D 3D coil operators")

    elif is_gaussian:
        # Derive RBF centres from sensor extent (mirrors OMFIT gaussian setup block)
        x_all = np.hstack((x1, x2))
        y_all = np.hstack((y1, y2))
        xlim = (int(np.min(x_all) / 10.0) * 10, int(np.ceil(np.max(x_all) / 10.0)) * 10)
        ylim = (int(np.min(y_all) / 10.0) * 10, int(np.ceil(np.max(y_all) / 10.0)) * 10)

        xend = True
        if xlim[1] - xlim[0] > 180:
            xlim = (0, 360)
            xend = False  # no duplicate at 0/360 for full-torus arrays
        yend = True
        if ylim[1] - ylim[0] > 180:
            ylim = (0, 360)
            yend = False

        ns_cen = np.linspace(xlim[0], xlim[1], ncenters, endpoint=xend)
        ms_cen = np.linspace(ylim[0], ylim[1], mcenters, endpoint=yend)

        _nepsilon = nepsilon
        if _nepsilon is None or _nepsilon == 0:
            _nepsilon = float(np.mean(np.diff(ns_cen))) if len(ns_cen) > 1 else np.inf

        _mepsilon = mepsilon
        if _mepsilon is None or _mepsilon == 0:
            _mepsilon = float(np.mean(np.diff(ms_cen))) if len(ms_cen) > 1 else np.inf

        _ncycle = max(1, int(8 * _nepsilon / 360)) if np.isfinite(_nepsilon) else 0
        _mcycle = max(1, int(8 * _mepsilon / 360)) if np.isfinite(_mepsilon) else 0

        nms = [(float(n), float(m)) for m in ms_cen for n in ns_cen]
        nms_arr = np.array(nms)
        _printv(
            f" - Gaussian RBF: {ncenters}×{mcenters} centres, "
            f"eps_phi={_nepsilon:.1f}°, eps_theta={'inf' if not np.isfinite(_mepsilon) else f'{_mepsilon:.1f}'}°, "
            f"ncycle={_ncycle}"
        )
    else:
        raise ValueError(
            f"fit_basis must start with 'sinusoidal' or 'gaussian', got {fit_basis!r}."
        )

    # ── design matrix A ───────────────────────────────────────────────────────
    A_cols = []
    ncomp = []

    if is_sinusoidal:
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
                except ValueError, np.linalg.LinAlgError:
                    logger.error(" - Ill-conditioned mode (%s,%s); fitting single component", n, m)
                    x0 = x1[0] + delta_degrees(x1[0], x2[0]) / 2.0
                    y0 = y1[0] + delta_degrees(y1[0], y2[0]) / 2.0
                    fmn = (
                        form_basis_function(n, m, x1 + x0, x2 + x0, y1 + y0, y2 + y0, fit_basis)
                        / sigma
                    )
                    A_cols = A_cols[:-2] + [fmn.real]
                    ncomp[-1] = 1
    else:  # gaussian — basis functions are always real
        for n, m in nms:
            fmn = (
                form_basis_function(
                    n,
                    m,
                    x1,
                    x2,
                    y1,
                    y2,
                    fit_basis,
                    ncycle=_ncycle,
                    mcycle=_mcycle,
                    nepsilon=_nepsilon,
                    mepsilon=_mepsilon,
                )
                / sigma
            )
            A_cols.append(fmn)
            ncomp.append(1)

    A = np.array(A_cols).T  # (n_sensors, n_columns)
    if A.shape[1] > A.shape[0]:
        logger.warning("Fitting %d basis functions with %d sensors", A.shape[1], A.shape[0])

    # ── SVD of A (condition number + per-coefficient error bars) ──────────────
    U_a, w_a, Vh_a = np.linalg.svd(A)
    c_a = np.abs(w_a[0] / w_a)
    valid = c_a <= fit_cond
    raw_cn = float(np.abs(w_a[0] / w_a[-1]))
    eff_cn = float(np.max(c_a[valid]))

    # ── least-squares fit at every time slice ─────────────────────────────────
    _printv(" - Fitting signal")
    b = (
        ds["signal"] / xr.DataArray(sigma, coords={"channel": ds["channel"]}, dims=("channel",))
    ).values
    x, residual, rank_fit, s_a = np.linalg.lstsq(A, b, rcond=1.0 / fit_cond)
    _printv(f" - Raw / effective condition number = {raw_cn:.3g} / {eff_cn:.3g}")
    fit_coeffs = np.asarray(x)  # (n_columns, n_time)

    # per-coefficient sigma from pseudo-inverse singular values
    w_inv = 1.0 / w_a
    w_inv[~valid] = 0.0
    w_inv = np.hstack((w_inv, [0.0] * max(Vh_a.shape[0] - w_a.shape[0], 0)))
    fit_sigma2 = np.sum((Vh_a.T * w_inv) ** 2, axis=0)
    fit_sigmas = np.sqrt(fit_sigma2)  # (n_columns,)

    # ── reform per-mode complex (sinusoidal) or real (Gaussian) coefficients ──
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

    # ── assemble output Dataset ───────────────────────────────────────────────
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

    ds.attrs.update(
        fit_basis=fit_basis,
        fit_geometry=fit_geometry,
        fit_condition=fit_cond,
        raw_cn=raw_cn,
        eff_cn=eff_cn,
        condition_number=raw_cn,
        fit_ncycle=_ncycle,
        fit_mcycle=_mcycle,
        fit_neps=_nepsilon,
        fit_meps=_mepsilon,
    )
    _condition_warning(raw_cn)
    return ds


def _condition_warning(K):
    """SLCONTOUR's K-thresholds (VISION S4.1): warn > 10, error > 20."""
    if K > 20:
        logger.error(
            "Condition number K = %.1f > 20: fit is untrustworthy (under-resolved array).", K
        )
    elif K > 10:
        logger.warning("Condition number K = %.1f > 10: fit may be poorly resolved.", K)
