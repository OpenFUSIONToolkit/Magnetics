"""Assemble GUI nodes from fetched shot data — orchestration only.

Each builder pulls real channels from the HDF5 (data/h5source), maps device
geometry (data/diiid), runs device-agnostic math (core/spectral, core/geometry),
and shapes the result with core/contracts. The web routes just call `build_node`.

Where the full SLCONTOUR/MODESPEC physics doesn't exist yet, we serve the real
underlying data with honest labels (e.g. raw δBp(φ,t) instead of a fitted φ–θ map)
rather than fake numbers.
"""
from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

import sys as _sys
from pathlib import Path as _Path
# magnetics-code/ is not an installed package — add it to the path so run_steps
# and the other scripts are importable. parents[3] = analysis/ from service/nodes.py
_MAGNETICS_CODE = str(_Path(__file__).parents[3] / "magnetics-code")
if _MAGNETICS_CODE not in _sys.path:
    _sys.path.insert(0, _MAGNETICS_CODE)

from ..core import contracts, geometry, spectral
from ..core import qs_bridge
from ..data import diiid, h5source

T_TO_GAUSS = 1.0e4  # PTDATA integrated field is ~Tesla; show Gauss like the GUI


# ── GUI param parsing (HTTP query params arrive as strings) ──────────────────
def _f(params, key, default=None):
    if not params or params.get(key) in (None, ""):
        return default
    try:
        return float(params[key])
    except (TypeError, ValueError):
        return default


def _i(params, key, default=None):
    v = _f(params, key, None)
    return int(v) if v is not None else default


def _flag(params, key) -> bool:
    return bool(params) and str(params.get(key, "")).lower() in ("1", "true", "yes", "on")


def machines() -> list[dict]:
    return h5source.list_shots()


def refresh() -> None:
    """Forget cached state (call after a new fetch writes a file)."""
    h5source.refresh()
    _spec_result.cache_clear()
    _qs_run.cache_clear()


def _array_channels(shot, families: tuple[str, ...]):
    """Channels present in this shot belonging to `families`, with a parseable
    phi, sorted by phi. Returns list of (name, phi)."""
    fam_set = set(families)
    out = []
    for name in h5source.channel_names(shot):
        if diiid.family_of(name) in fam_set:
            phi = diiid.phi_of(name)
            if phi is not None:
                out.append((name, phi))
    out.sort(key=lambda np_: np_[1])
    return out


def _stack(shot, names):
    """Load channels, truncate to common length, return (t_ms, matrix[ch,time]).

    A toroidal/poloidal array shares one digitizer clock, so only the first
    channel's time axis is needed: read time once (the reference channel) and
    data-only for the rest, instead of materializing every channel's time vector.
    """
    t0, d0 = h5source.load_channel(shot, names[0])
    datas = [d0] + [h5source.load_data(shot, nm) for nm in names[1:]]
    nmin = min(d.size for d in datas)
    t = t0[:nmin]
    mat = np.array([d[:nmin] for d in datas], dtype=float)
    return t, mat


# ── geometry: sensor φ–θ wall map ────────────────────────────────────────────
def _geometry(shot, params=None) -> dict:
    points = []
    for name in h5source.channel_names(shot):
        s = diiid.sensor(name)
        if s["phi"] is None:
            continue
        points.append({"x": s["phi"], "y": s["theta"],
                       "label": s["family"], "group": s["family"]})
    if not points:
        raise ValueError("no sensors with a parseable toroidal angle")
    return contracts.scatter2d(
        points, {"x": "φ (deg)", "y": "θ (deg)"},
        meta={"n_sensors": len(points), "shot": str(shot),
              "note": "θ is approximate (no geometry table yet)"})


# ── spectrogram: real 2-point MODESPEC cross-spectrogram ─────────────────────
def _pick_pair(shot) -> tuple[tuple[str, float], tuple[str, float]]:
    """Two toroidally-separated probes for the 2-point cross-spectrogram.
    Prefer the fast Mirnov dB/dt array (MPI_BDOT), then integrated Bp (MPID).
    Returns ((name1, phi1), (name2, phi2)) with the widest non-zero separation."""
    for families in (("MPI_BDOT",), ("MPID",), ("MPI_BDOT", "MPID", "MPIF")):
        arr = _array_channels(shot, families)        # (name, phi), sorted by phi
        if len(arr) >= 2 and arr[0][1] != arr[-1][1]:
            return arr[0], arr[-1]
    raise ValueError("need two toroidally-separated probes for a spectrogram")


@lru_cache(maxsize=8)
def _spec_result(shot: str, slice_duration: float, coherence_smooth: int):
    """The (expensive) STFT, cached so the spectrogram/n-map/coherence/n-spectrum
    nodes share one compute. Keyed on the STFT-shaping params only; cheap post-ops
    (freq crop, denoise) are applied per node. Returns (result, probes, delta_phi)."""
    (n1, phi1), (n2, phi2) = _pick_pair(shot)
    t1, s1 = h5source.load_channel(shot, n1)
    t2, s2 = h5source.load_channel(shot, n2)
    k = min(t1.size, s1.size, t2.size, s2.size)
    if k < 256:
        raise ValueError(f"channels too short for a spectrogram ({k} samples)")
    time_s = np.asarray(t1[:k], dtype=float) * 1e-3   # HDF5 time base is ms
    res = spectral.compute_spectrogram(
        time_s, s1[:k], s2[:k], delta_phi=float(phi2 - phi1),
        slice_duration=slice_duration, coherence_smooth=coherence_smooth)
    return res, (n1, n2), round(float(phi2 - phi1), 1)


def _prep_spec(shot, params):
    """Resolve params → a (possibly denoised) SpectrogramResult + a frequency mask.
    Shared by all spectrogram-derived nodes so a knob change re-runs the core."""
    sd = _f(params, "slice_duration", 0.001)
    cs = _i(params, "coherence_smooth", None)
    if cs is None:
        cs = _i(params, "smoothing", 5)
    res, probes, dphi = _spec_result(str(shot), sd, max(2, cs))
    if _flag(params, "denoise"):
        res = spectral.denoise_spectrogram(res, coherence_min=_f(params, "coherence_min", 0.5))
    f_khz = np.asarray(res.frequency) / 1e3
    mask = np.ones(f_khz.size, dtype=bool)
    fmin, fmax = _f(params, "fmin"), _f(params, "fmax")
    if fmin is not None:
        mask &= f_khz >= fmin
    if fmax is not None:
        mask &= f_khz <= fmax
    return res, mask, probes, dphi


def _spectrogram(shot, params=None) -> dict:
    res, mask, probes, dphi = _prep_spec(shot, params)
    f = np.asarray(res.frequency)[mask] / 1e3
    # power is [n_times, n_freqs]; heatmap z is [i_y=freq][i_x=time] → transpose.
    z = np.log10(np.maximum(np.asarray(res.power, dtype=float)[:, mask].T, 1e-30))
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(), f.tolist(), z.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "log₁₀ power"},
        discrete=False,
        meta={"probes": list(probes), "delta_phi_deg": dphi, "shot": str(shot)})


def _mode_number(shot, params=None) -> dict:
    """Real toroidal mode-number n(t,f) — n = round(phase/Δφ) from the core."""
    res, mask, probes, dphi = _prep_spec(shot, params)
    f = np.asarray(res.frequency)[mask] / 1e3
    n = np.asarray(res.mode_number, dtype=float)[:, mask]
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(), f.tolist(), n.T.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "toroidal n"},
        discrete=True, zrange=[-6.5, 6.5],
        meta={"probes": list(probes), "delta_phi_deg": dphi, "shot": str(shot)})


def _coherence(shot, params=None) -> dict:
    """Real 2-point coherence γ²(t,f) in [0,1] from the core."""
    res, mask, probes, _dphi = _prep_spec(shot, params)
    f = np.asarray(res.frequency)[mask] / 1e3
    coh = np.asarray(res.coherence, dtype=float)[:, mask]
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(), f.tolist(), coh.T.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "coherence"},
        discrete=False, zrange=[0.0, 1.0],
        meta={"probes": list(probes), "shot": str(shot)})


def _n_spectrum(shot, params=None) -> dict:
    """RMS amplitude per toroidal mode number vs time (the n-spectrum)."""
    res, _mask, probes, _dphi = _prep_spec(shot, params)
    rms = np.asarray(res.rms_by_mode, dtype=float)   # [n_times, n_modes]
    modes = np.asarray(res.mode_indices)             # [n_modes]
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(), modes.tolist(), rms.T.tolist(),
        {"x": "time (ms)", "y": "toroidal n", "z": "rms amplitude"},
        discrete=False,
        meta={"probes": list(probes), "shot": str(shot)})


# ── shared grid builder for contour and phi_t ────────────────────────────────
def _toroidal_grid(shot):
    """Interpolate toroidal MPID channels onto a regular φ×t grid.

    Returns (t_sub_ms, phi_grid_deg, z, raw_phis, n_channels) where
    z has shape (n_time, n_phi) — i.e. z[time_idx, phi_idx].
    """
    for families in (("MPID",), ("MPI_BDOT",)):
        arr = _array_channels(shot, families)
        if len(arr) >= 4:
            break
    if len(arr) < 4:
        raise ValueError("not enough toroidal-array channels for a map (need ≥ 4)")
    names = [n for n, _ in arr]
    phis = np.array([p for _, p in arr])
    t_ms, mat = _stack(shot, names)
    nt = min(160, t_ms.size)
    ti = np.linspace(0, t_ms.size - 1, nt).astype(int)
    t_sub = t_ms[ti]
    vals = mat[:, ti] * T_TO_GAUSS
    phi_grid = np.linspace(0, 360, 73)
    z = np.empty((nt, phi_grid.size))
    order = np.argsort(phis)
    pe = np.concatenate([phis[order], phis[order][:1] + 360.0])
    for j in range(nt):
        ve = np.concatenate([vals[order, j], vals[order, j][:1]])
        z[j] = np.interp(phi_grid, pe, ve)
    return t_sub, phi_grid, z, phis, len(names)


# ── contour: raw δBp(φ, t) — x=φ, y=time (QS contour hero plot) ──────────────
def _contour(shot, params=None) -> dict:
    t_sub, phi_grid, z, phis, n_ch = _toroidal_grid(shot)
    zmax = float(np.nanmax(np.abs(z))) or 1.0
    overlay = {"points": [{"x": float(p), "y": float(t_sub[0])} for p in phis],
               "symbol": "square"}
    return contracts.contour(
        phi_grid.tolist(), t_sub.tolist(), z.tolist(),
        {"x": "φ (deg)", "y": "time (ms)", "z": "δBp (G)"},
        zrange=[-zmax, zmax], overlay=overlay,
        meta={"channels": n_ch, "shot": str(shot),
              "note": "raw toroidal δBp(φ,t) — SLCONTOUR φ–θ fit pending"})


# ── phi_t: SLCONTOUR φ–t contour from fit reconstruction ─────────────────────
def _phi_t(shot, params=None) -> dict:
    """Reconstructed δBp(φ, t) at fixed θ=0 — the SLCONTOUR waterfall plot.

    Mirrors plots.plot_slice(r.fit, fix_coord='theta', fix_value=0.0).
    Rotating modes appear as diagonal stripes; locked modes as vertical bands.
    """
    return qs_bridge.fit_to_phi_t_node(_prep_qs_ds(shot, params).fit)


# ── fit_quality: condition number K + χ² from the SLCONTOUR fit ──────────────
def _fit_quality(shot, params=None) -> dict:
    """Fit quality metrics — uses the full run_steps fit when available."""
    try:
        return qs_bridge.fit_to_fit_quality_node(_prep_qs_ds(shot, params).fit)
    except Exception:
        pass
    # Fallback: geometry-only K (no fit available yet)
    arr = _array_channels(shot, ("MPID",))
    if len(arr) < 4:
        arr = _array_channels(shot, ("MPI_BDOT",))
    m = h5source.meta(shot)
    fields = [{"label": "shot", "value": str(m["shot"])},
              {"label": "channels fetched", "value": m["n_channels"]}]
    if len(arr) >= 7:
        phis = [p for _, p in arr]
        k = geometry.condition_number(phis, n_max=3)
        fields.insert(0, {"label": "condition number K (n≤3)",
                          "value": round(k, 2),
                          "status": contracts.quality_for_k(k)})
        fields.append({"label": "toroidal-array channels", "value": len(arr)})
    else:
        fields.append({"label": "condition number K",
                       "value": "n/a (no toroidal array in this pull)"})
    return contracts.metrics("Fit quality", fields,
                             meta={"note": "geometry-only K; full fit unavailable"})


# ── phase_fit: phase-vs-φ at one frequency, at the GUI time cursor ────────────
def _phase_fit(shot, params=None) -> dict:
    arr = _array_channels(shot, ("MPI_BDOT", "MPID"))
    if len(arr) < 4:
        raise ValueError("not enough toroidal-array channels for a phase fit")
    names = [n for n, _ in arr]
    phis = np.array([p for _, p in arr], dtype=float)
    t_ms, mat = _stack(shot, names)               # mat[ch, time]
    f_khz = _f(params, "f_khz", 5.0)
    # honor the GUI time cursor: a small window around t0 (ms) → t_range (s)
    t0_ms = _f(params, "time", None)
    t_range = None
    if t0_ms is not None:
        w = _f(params, "window_ms", 2.0)
        t_range = ((t0_ms - w) * 1e-3, (t0_ms + w) * 1e-3)
    mode = spectral.extract_mode_at_frequency(
        mat, phis, np.asarray(t_ms, dtype=float) * 1e-3,
        frequency=f_khz * 1e3, t_range=t_range)
    fit = spectral.fit_toroidal_mode(mode)        # best-fit toroidal n
    points = [{"x": float(p), "y": float(ph), "group": diiid.kind_of(nm)}
              for (nm, p), ph in zip(arr, mode.phase)]
    line = {"x": [0.0, 360.0],
            "y": [fit.intercept_deg, fit.intercept_deg + fit.n * 360.0]}
    return contracts.scatter2d(
        points, {"x": "φ (deg)", "y": "phase (deg)"}, fit=line,
        meta={"n_estimate": fit.n, "resultant": round(float(fit.resultant), 3),
              "f_kHz": f_khz, "t0_ms": t0_ms, "shot": str(shot),
              "note": "MODESPEC phase-at-frequency + circular n-fit"})


# ── quasi-stationary fit (SLCONTOUR via magnetics-code pipeline) ─────────────

_QS_RUN_LOCK = threading.Lock()


@lru_cache(maxsize=8)
def _qs_run(shot: str, ns: tuple, ms: tuple, channel_filter: str,
            detrend_type: str, detrend_band: tuple,
            cutoff_lo: float, cutoff_hi: float, energy: float,
            tmin_s: float, tmax_s: float):
    """Run the full SLCONTOUR pipeline (io_data → prep → fit) for one shot.

    Delegates to magnetics-code/run.run_steps. All tuning parameters are
    explicit cache-key arguments so the result is reused across node requests
    that share the same settings. tmin_s/tmax_s are in seconds and come from
    _prep_qs_ds (which reads HDF5 defaults and applies any user override).
    """
    from run import run_steps  # magnetics-code/run.py on sys.path

    # detrend_band is in ms from the GUI; (0, 0) = auto → first 10ms of shot window
    if detrend_band == (0.0, 0.0):
        db_lo_s, db_hi_s = tmin_s, tmin_s + 0.01
    else:
        db_lo_s = max(detrend_band[0] / 1e3, tmin_s)
        db_hi_s = min(detrend_band[1] / 1e3, tmax_s)

    r = run_steps(
        shot,
        channel_filter=channel_filter,
        ns=ns,
        ms=ms,
        time_trim=(tmin_s, tmax_s),
        prep_kwargs=dict(
            cutoff_hz=(cutoff_lo, cutoff_hi),
            energy=energy,
            detrend_type=detrend_type,
            detrend_band=(db_lo_s, db_hi_s),
        ),
        verbose=False,
    )
    return r


def _prep_qs_ds(shot, params):
    """Parse GUI query params and return the full MagneticsRun object."""
    import h5py

    ns_raw = params.get("ns", "1,2,3") if params else "1,2,3"
    ms_raw = params.get("ms", "0") if params else "0"
    ns = tuple(int(x.strip()) for x in str(ns_raw).split(",") if x.strip())
    ms = tuple(int(x.strip()) for x in str(ms_raw).split(",") if x.strip())
    channel_filter = (params.get("channel_filter", "Bp_LFS_midplane") if params
                      else "Bp_LFS_midplane")
    detrend_type = params.get("detrend_type", "baseline") if params else "baseline"
    # detrend_band: GUI sends absolute ms values. When absent, use sentinel (0,0)
    # so _qs_run defaults to the first 10ms of the shot window.
    db_lo_str = params.get("detrend_lo") if params else None
    db_hi_str = params.get("detrend_hi") if params else None
    if db_lo_str is None or db_hi_str is None:
        db_lo, db_hi = 0.0, 0.0  # sentinel: auto
    else:
        db_lo, db_hi = float(db_lo_str), float(db_hi_str)
    cutoff_lo = float(params.get("cutoff_lo", 5.0)) if params else 5.0
    cutoff_hi = float(params.get("cutoff_hi", 250.0)) if params else 250.0
    energy = float(params.get("energy", 0.98)) if params else 0.98

    # Time trim: read shot-window defaults from HDF5, then apply any user override.
    path = h5source.shot_file(str(shot))
    with h5py.File(str(path), "r") as f:
        tmin_s_auto = float(f.attrs.get("tmin", 0)) / 1e3
        tmax_s_auto = float(f.attrs.get("tmax", 0)) / 1e3
    tmin_ms_str = params.get("tmin_ms") if params else None
    tmax_ms_str = params.get("tmax_ms") if params else None
    tmin_s = float(tmin_ms_str) / 1e3 if tmin_ms_str else tmin_s_auto
    tmax_s = float(tmax_ms_str) / 1e3 if tmax_ms_str else tmax_s_auto

    # Serialize concurrent calls with the same args: only one thread runs
    # run_steps; the others wait and then read the cached result instantly.
    with _QS_RUN_LOCK:
        return _qs_run(str(shot), ns, ms, channel_filter, detrend_type,
                       (db_lo, db_hi), cutoff_lo, cutoff_hi, energy,
                       tmin_s, tmax_s)


def _qs_fit(shot, params=None) -> dict:
    """Reconstructed δBp(φ, θ) spatial map at the GUI time cursor → ContourNode."""
    run = _prep_qs_ds(shot, params)
    t0 = _f(params, "time", None)
    return qs_bridge.fit_to_qs_fit_node(run.fit, t0_ms=t0)


def _amplitude(shot, params=None) -> dict:
    """Mode amplitude ± 1σ vs time → LineNode."""
    return qs_bridge.fit_to_amplitude_node(_prep_qs_ds(shot, params).fit)


def _phase_t(shot, params=None) -> dict:
    """Mode phase ± 1σ vs time → LineNode."""
    return qs_bridge.fit_to_phase_t_node(_prep_qs_ds(shot, params).fit)


# ── sensor maps ──────────────────────────────────────────────────────────────

def _no_wrap(a):
    """Avoid mis-plotting sensors that straddle an angle wrap (>240° span)."""
    x = np.array(a, dtype=float)
    if np.ptp(x) > 240:
        x[x == x.min()] += 360
    return x.tolist()


def _sensor_map_rz(shot, params=None) -> dict:
    """Sensor locations in device cross-section (R-Z) for selected channels."""
    run = _prep_qs_ds(shot, params)
    raw = run.raw
    channels = list(run.prepared["channel"].values)
    device = str(raw.attrs.get("device", "DIII-D"))

    from omfit_compat import load_wall  # magnetics-code/ on sys.path
    r_wall, z_wall = load_wall(device)

    series = []
    for c in channels:
        s = raw.sel(channel=c)
        r1, r2 = float(s["r_end1"]), float(s["r_end2"])
        z1, z2 = float(s["z_end1"]), float(s["z_end2"])
        series.append({"name": c, "x": [r1, r2], "y": [z1, z2]})

    wall = None
    if r_wall is not None:
        wall = {"x": r_wall.tolist(), "y": z_wall.tolist()}

    return contracts.line(series, {"x": "R (m)", "y": "z (m)"},
                          meta={"wall": wall, "shot": str(shot), "channels": channels,
                                "note": "sensor extent segments from device geometry"})


def _sensor_map_cylindrical(shot, params=None) -> dict:
    """Sensor locations in unrolled φ-θ space for selected channels."""
    run = _prep_qs_ds(shot, params)
    raw = run.raw
    channels = list(run.prepared["channel"].values)

    series = []
    for c in channels:
        s = raw.sel(channel=c)
        p1, p2 = float(s["phi_end1"]), float(s["phi_end2"])
        t1, t2 = float(s["theta_end1"]), float(s["theta_end2"])
        x = _no_wrap([p1, p2, p2, p1, p1])
        y = _no_wrap([t1, t1, t2, t2, t1])
        series.append({"name": c, "x": x, "y": y})

    return contracts.line(series, {"x": "φ (deg)", "y": "θ (deg)"},
                          meta={"shot": str(shot), "channels": channels})


# ── signal conditioning ───────────────────────────────────────────────────────

def _signal_conditioning(shot, params=None) -> dict:
    """Raw vs prepared signals for the selected channel subset."""
    run = _prep_qs_ds(shot, params)
    return qs_bridge.prepared_to_signal_node(run.raw, run.prepared)


# ── fit quality time series (chi-squared, fitted signals, residuals) ──────────

def _chi_sq_t(shot, params=None) -> dict:
    """Reduced χ² vs time → LineNode (log scale, reference at 1)."""
    return qs_bridge.fit_to_chi_sq_node(_prep_qs_ds(shot, params).fit)


def _fit_signals(shot, params=None) -> dict:
    """Fitted signal per channel vs time → LineNode (Section 6 middle panel)."""
    return qs_bridge.fit_to_fit_signals_node(_prep_qs_ds(shot, params).fit)


def _fit_residuals(shot, params=None) -> dict:
    """Fit residuals per channel vs time → LineNode (Section 6 bottom panel)."""
    return qs_bridge.fit_to_fit_residuals_node(_prep_qs_ds(shot, params).fit)


_BUILDERS = {
    "geometry": _geometry,
    "spectrogram": _spectrogram,
    "mode_number": _mode_number,
    "coherence": _coherence,
    "n_spectrum": _n_spectrum,
    "contour": _contour,
    "phi_t": _phi_t,
    "qs_fit": _qs_fit,
    "amplitude": _amplitude,
    "phase_t": _phase_t,
    "fit_quality": _fit_quality,
    "phase_fit": _phase_fit,
    # QS sensor map + conditioning + fit-quality time series
    "sensor_map_rz": _sensor_map_rz,
    "sensor_map_cylindrical": _sensor_map_cylindrical,
    "signal_conditioning": _signal_conditioning,
    "chi_sq_t": _chi_sq_t,
    "fit_signals": _fit_signals,
    "fit_residuals": _fit_residuals,
}


def build_node(shot: str, node_id: str, params: dict | None = None) -> dict:
    if node_id not in _BUILDERS:
        raise KeyError(f"unknown node {node_id!r}; "
                       f"have {', '.join(sorted(_BUILDERS))}")
    h5source.shot_file(shot)  # raises KeyError if the shot isn't available
    return _BUILDERS[node_id](shot, params)
