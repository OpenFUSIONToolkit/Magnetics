"""Adapt fit.py's xarray Dataset output → GUI kind-node dicts.

Pure output-side bridge — no data loading, no fit logic. Takes the Dataset
produced by ``magnetics-code/fit.fit()`` (or any equivalent) and converts it
to the JSON contract consumed by the GUI's NodeView / Plot components.

Input contract (fit Dataset variables):
    fit_ns   [mode]       — toroidal mode numbers (float, stored as signed for helicity)
    fit_ms   [mode]       — poloidal mode numbers
    fit_coeffs [mode, time] — complex fitted coefficients
    fit_sigmas [mode, time] — complex 1-σ errors (same value at every t; shape for broadcast)
    red_chi_sq [time]     — reduced chi-squared
    basis    [basis_channel, basis_mode] — design matrix A (for SVD diagnostics)
    time     [time]       — time coordinate; assumed seconds, converted to ms here

Dataset attrs used:
    condition_number, raw_cn, eff_cn — fit condition numbers
    fit_condition — fit_cond threshold
    shot

Output contract: dicts matching core/contracts.py (ContourNode, LineNode, MetricsNode).
"""
from __future__ import annotations

import numpy as np

# fit.py works in Tesla (raw HDF5 units); the GUI and plots.py show Gauss
_T_TO_G = 1.0e4


# ── internal helpers ──────────────────────────────────────────────────────────

def _time_ms(fit_ds) -> np.ndarray:
    """Return time in milliseconds. fit.py stores time in seconds."""
    return np.asarray(fit_ds["time"].values, dtype=float) * 1e3


def _amp_phase(coeff: np.ndarray, sigma: np.ndarray):
    """Amplitude / phase and 1-σ errors. Direct port of plots._amp_phase_with_errors."""
    c, s = coeff.real, coeff.imag
    ec, es = sigma.real, sigma.imag
    amp = np.sqrt(c ** 2 + s ** 2)
    denom = np.where(amp == 0, np.nan, amp)
    amp_err = np.sqrt((c * ec) ** 2 + (s * es) ** 2) / denom
    phase = np.rad2deg(np.arctan2(s, c))
    p2 = np.where((c ** 2 + s ** 2) == 0, np.nan, c ** 2 + s ** 2)
    phase_err = np.rad2deg(np.sqrt((c * es) ** 2 + (s * ec) ** 2) / p2)
    return amp, np.nan_to_num(amp_err), phase, np.nan_to_num(phase_err)


def _mode_label(n: int | float, m: int | float) -> str:
    n, m = int(round(n)), int(round(m))
    return f"n={n}" if m == 0 else f"m/n={m}/{n}"


def _quality_status(K: float) -> str:
    if K > 20:
        return "error"
    if K > 10:
        return "warn"
    return "ok"


def _reconstruct_grid(fit_ds, phi_grid: np.ndarray, theta_grid: np.ndarray, t_idx: int) -> np.ndarray:
    """Reconstruct δBp on a (phi, theta) grid at one time index.

    Uses plot_slice's sign convention: exp(-i*(n*phi + m*theta)).
    Returns z[n_theta, n_phi].
    """
    phi_rad = np.deg2rad(phi_grid)      # [n_phi]
    theta_rad = np.deg2rad(theta_grid)  # [n_theta]
    ns = fit_ds["fit_ns"].values         # [n_mode]
    ms = fit_ds["fit_ms"].values         # [n_mode]
    coeffs_t = fit_ds["fit_coeffs"].values[:, t_idx]  # [n_mode] complex

    z = np.zeros((len(theta_grid), len(phi_grid)))
    for i, (n, m) in enumerate(zip(ns, ms)):
        c = coeffs_t[i]
        # outer: [n_theta, n_phi] — sign matches plot_slice reconstruction
        phase = np.exp(-1j * m * theta_rad)[:, None] * np.exp(-1j * n * phi_rad)[None, :]
        z += (c * phase).real
    return z


# ── public adapters ───────────────────────────────────────────────────────────

def fit_to_qs_fit_node(
    fit_ds,
    t0_ms: float | None = None,
    phi_grid: np.ndarray | None = None,
    theta_grid: np.ndarray | None = None,
    sensor_phis: np.ndarray | None = None,
    sensor_thetas: np.ndarray | None = None,
) -> dict:
    """Reconstructed δBp(φ, θ) spatial map at cursor time → ContourNode.

    Parameters
    ----------
    fit_ds      : xarray Dataset from fit.fit()
    t0_ms       : cursor time in ms; defaults to shot midpoint
    phi_grid    : toroidal grid in degrees (default 0-360, 73 points)
    theta_grid  : poloidal grid in degrees (default 0-360, 49 points)
    sensor_phis, sensor_thetas : overlay points in degrees; optional
    """
    from ..core import contracts

    t_ms = _time_ms(fit_ds)
    if t0_ms is None:
        t0_ms = float(np.median(t_ms))
    t_idx = int(np.argmin(np.abs(t_ms - t0_ms)))

    if phi_grid is None:
        phi_grid = np.linspace(0, 360, 73)
    if theta_grid is None:
        theta_grid = np.linspace(0, 360, 49)

    z = _reconstruct_grid(fit_ds, phi_grid, theta_grid, t_idx) * _T_TO_G
    zmax = float(np.nanmax(np.abs(z))) or 1.0

    overlay = None
    if sensor_phis is not None and sensor_thetas is not None:
        overlay = {
            "points": [{"x": float(p), "y": float(th)}
                       for p, th in zip(sensor_phis, sensor_thetas)],
            "symbol": "square",
        }

    ns = fit_ds["fit_ns"].values
    ms = fit_ds["fit_ms"].values
    coeffs_t = fit_ds["fit_coeffs"].values[:, t_idx]
    dominant_idx = int(np.argmax(np.abs(coeffs_t)))
    K = float(fit_ds.attrs.get("condition_number", fit_ds.attrs.get("raw_cn", 0.0)))

    chi2_t = float(fit_ds["red_chi_sq"].values[t_idx])

    return contracts.contour(
        phi_grid.tolist(),
        theta_grid.tolist(),
        np.round(z, 4).tolist(),
        {"x": "φ (deg)", "y": "θ (deg)", "z": "δBp (G)"},
        zrange=[-zmax, zmax],
        overlay=overlay,
        meta={
            "n": int(round(ns[dominant_idx])),
            "m": int(round(ms[dominant_idx])),
            "condition_number": round(K, 2),
            "red_chi_sq": round(chi2_t, 3),
            "shot": str(fit_ds.attrs.get("shot", "")),
        },
    )


def fit_to_amplitude_node(fit_ds) -> dict:
    """Mode amplitude ± 1σ vs time for each fitted mode → LineNode.

    meta.sigma[i] is the per-series error band consumed by lineTraces() in the GUI.
    """
    from ..core import contracts

    t_ms = _time_ms(fit_ds)
    ns = fit_ds["fit_ns"].values
    ms_vals = fit_ds["fit_ms"].values
    coeffs = fit_ds["fit_coeffs"].values   # [mode, time] complex
    sigmas = fit_ds["fit_sigmas"].values   # [mode, time] complex (constant along time)

    series = []
    sigma_bands = []
    for i, (n, m) in enumerate(zip(ns, ms_vals)):
        amp, amp_err, _, _ = _amp_phase(coeffs[i], sigmas[i])
        series.append({
            "name": _mode_label(n, m),
            "x": np.round(t_ms, 2).tolist(),
            "y": np.round(amp * _T_TO_G, 4).tolist(),
        })
        sigma_bands.append(np.round(amp_err * _T_TO_G, 4).tolist())

    K = float(fit_ds.attrs.get("condition_number", fit_ds.attrs.get("raw_cn", 0.0)))
    return contracts.line(
        series,
        {"x": "time (ms)", "y": "amplitude (G)"},
        meta={
            "sigma": sigma_bands,
            "condition_number": round(K, 2),
            "shot": str(fit_ds.attrs.get("shot", "")),
        },
    )


def fit_to_phase_t_node(fit_ds) -> dict:
    """Mode phase ± 1σ vs time for each fitted mode → LineNode.

    Flat phase = locked mode; winding ramp = rotating mode.
    """
    from ..core import contracts

    t_ms = _time_ms(fit_ds)
    ns = fit_ds["fit_ns"].values
    ms_vals = fit_ds["fit_ms"].values
    coeffs = fit_ds["fit_coeffs"].values
    sigmas = fit_ds["fit_sigmas"].values

    series = []
    sigma_bands = []
    for i, (n, m) in enumerate(zip(ns, ms_vals)):
        _, _, phase, phase_err = _amp_phase(coeffs[i], sigmas[i])
        series.append({
            "name": _mode_label(n, m),
            "x": np.round(t_ms, 2).tolist(),
            "y": np.round(phase, 3).tolist(),
        })
        sigma_bands.append(np.round(phase_err, 3).tolist())

    K = float(fit_ds.attrs.get("condition_number", fit_ds.attrs.get("raw_cn", 0.0)))
    return contracts.line(
        series,
        {"x": "time (ms)", "y": "phase (deg)"},
        meta={
            "sigma": sigma_bands,
            "condition_number": round(K, 2),
            "shot": str(fit_ds.attrs.get("shot", "")),
        },
    )


def fit_to_fit_quality_node(fit_ds) -> dict:
    """Condition number, χ², channel count → MetricsNode for the quality panel."""
    from ..core import contracts

    K = float(fit_ds.attrs.get("condition_number", fit_ds.attrs.get("raw_cn", 0.0)))
    eff_cn = float(fit_ds.attrs.get("eff_cn", K))
    mean_chi2 = float(np.nanmean(fit_ds["red_chi_sq"].values))
    n_ch = int(fit_ds.sizes.get("channel", fit_ds["fit_sigmas"].shape[0]))
    fit_cond = float(fit_ds.attrs.get("fit_condition", 10.0))
    n_modes = int(fit_ds.sizes["mode"])

    return contracts.metrics(
        title="fit quality",
        fields=[
            {"label": "K (raw)",  "value": f"{K:.1f}",       "status": _quality_status(K)},
            {"label": "K (eff)",  "value": f"{eff_cn:.1f}",  "status": _quality_status(eff_cn)},
            {"label": "K cutoff", "value": f"{fit_cond:.0f}"},
            {"label": "χ² (mean)","value": f"{mean_chi2:.3f}"},
            {"label": "channels", "value": n_ch},
            {"label": "modes",    "value": n_modes},
        ],
    )


def fit_to_phi_t_node(fit_ds, theta_fixed_deg: float = 0.0, n_phi: int = 73) -> dict:
    """φ vs time contour (SLCONTOUR-style locked-mode picture) → ContourNode.

    Reconstructs the fitted field at fixed theta = theta_fixed_deg over all
    times and phi. Rotating modes appear as diagonal stripes; locking makes
    them horizontal. Mirrors plot_slice(fix_coord='theta').
    """
    from ..core import contracts

    t_ms = _time_ms(fit_ds)
    phi_grid = np.linspace(0, 360, n_phi)
    phi_rad = np.deg2rad(phi_grid)
    theta_rad = np.deg2rad(theta_fixed_deg)

    ns = fit_ds["fit_ns"].values       # [n_mode]
    ms = fit_ds["fit_ms"].values       # [n_mode]
    coeffs = fit_ds["fit_coeffs"].values  # [n_mode, n_time] complex

    # field[n_phi, n_time] = Re Sum_m coeff[m,t] * exp(-i*(n*phi + m*theta))
    n_t = len(t_ms)
    z = np.zeros((n_phi, n_t))
    for i, (n, m) in enumerate(zip(ns, ms)):
        phase_phi   = np.exp(-1j * n * phi_rad)[:, None]   # [n_phi, 1]
        phase_theta = np.exp(-1j * m * theta_rad)           # scalar complex
        z += (coeffs[i][None, :] * phase_phi * phase_theta).real
    z *= _T_TO_G

    zmax = float(np.nanpercentile(np.abs(z), 99)) or 1.0
    K = float(fit_ds.attrs.get("condition_number", fit_ds.attrs.get("raw_cn", 0.0)))

    # z shape: [n_phi, n_time] but ContourNode z is [n_y][n_x]
    # x = time (ms), y = phi (deg) → z[n_phi][n_time] is already correct
    return contracts.contour(
        np.round(t_ms, 2).tolist(),
        phi_grid.tolist(),
        np.round(z, 4).tolist(),
        {"x": "time (ms)", "y": "φ (deg)", "z": "δBp (G)"},
        zrange=[-zmax, zmax],
        meta={
            "theta_fixed_deg": theta_fixed_deg,
            "condition_number": round(K, 2),
            "shot": str(fit_ds.attrs.get("shot", "")),
            "note": "SLCONTOUR φ–t at fixed θ",
        },
    )
