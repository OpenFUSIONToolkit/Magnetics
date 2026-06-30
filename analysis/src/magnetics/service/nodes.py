"""Assemble GUI nodes from fetched shot data — orchestration only.

Each builder pulls real channels from the HDF5 (data/h5source), maps device
geometry (data/diiid), runs device-agnostic math (core/spectral, core/geometry),
and shapes the result with core/contracts. The web routes just call `build_node`.

Where the full SLCONTOUR/MODESPEC physics doesn't exist yet, we serve the real
underlying data with honest labels (e.g. raw δBp(φ,t) instead of a fitted φ–θ map)
rather than fake numbers.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from ..core import contracts, geometry, spectral
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


# ── contour: raw δBp(φ, t) over the toroidal array (fit pending) ──────────────
def _contour(shot, params=None) -> dict:
    arr = _array_channels(shot, ("MPID",))
    if len(arr) < 4:
        raise ValueError("not enough MPID toroidal-array channels for a map")
    names = [n for n, _ in arr]
    phis = np.array([p for _, p in arr])
    t_ms, mat = _stack(shot, names)            # mat[ch, time], Tesla-ish
    # subsample time for transport
    nt = min(160, t_ms.size)
    ti = np.linspace(0, t_ms.size - 1, nt).astype(int)
    t_sub = t_ms[ti]
    vals = mat[:, ti] * T_TO_GAUSS             # [ch, time] in Gauss
    # interpolate over phi onto a regular grid at each time (periodic)
    phi_grid = np.linspace(0, 360, 73)
    z = np.empty((nt, phi_grid.size))
    order = np.argsort(phis)
    pe = np.concatenate([phis[order], phis[order][:1] + 360.0])
    for j in range(nt):
        ve = np.concatenate([vals[order, j], vals[order, j][:1]])
        z[j] = np.interp(phi_grid, pe, ve)
    zmax = float(np.nanmax(np.abs(z))) or 1.0
    overlay = {"points": [{"x": float(p), "y": float(t_sub[0])} for p in phis],
               "symbol": "square"}
    return contracts.contour(
        phi_grid.tolist(), t_sub.tolist(), z.tolist(),
        {"x": "φ (deg)", "y": "time (ms)", "z": "δBp (G)"},
        zrange=[-zmax, zmax], overlay=overlay,
        meta={"channels": len(names), "shot": str(shot),
              "note": "raw toroidal δBp(φ,t) — SLCONTOUR φ–θ fit pending"})


# ── fit_quality: real condition number K of the toroidal array ───────────────
def _fit_quality(shot, params=None) -> dict:
    arr = _array_channels(shot, ("MPID",))
    m = h5source.meta(shot)
    fields = [{"label": "shot", "value": str(m["shot"])},
              {"label": "analysis", "value": m["analysis"]},
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
                             meta={"note": "K from the Fourier design matrix; "
                                           "χ² pending the full fit"})


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


_BUILDERS = {
    "geometry": _geometry,
    "spectrogram": _spectrogram,
    "mode_number": _mode_number,
    "coherence": _coherence,
    "n_spectrum": _n_spectrum,
    "contour": _contour,
    "fit_quality": _fit_quality,
    "phase_fit": _phase_fit,
}


def build_node(shot: str, node_id: str, params: dict | None = None) -> dict:
    if node_id not in _BUILDERS:
        raise KeyError(f"unknown node {node_id!r}; "
                       f"have {', '.join(sorted(_BUILDERS))}")
    h5source.shot_file(shot)  # raises KeyError if the shot isn't available
    return _BUILDERS[node_id](shot, params)
