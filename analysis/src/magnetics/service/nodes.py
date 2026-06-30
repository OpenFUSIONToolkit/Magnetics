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

from ..core import contracts, geometry, mode_shape, spectral
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
    for fn in (_spec_result, _stack_cached, _array_spectrum):
        fn.cache_clear()


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


@lru_cache(maxsize=1)
def _real_theta() -> dict:
    """name → real poloidal angle θ (deg) from the published DIII-D layout in
    ``_real_geometry`` (the genuine static positions), unioned over machines. Lets
    the poloidal arrays carry physical θ instead of ``diiid``'s cosmetic offset."""
    from . import _real_geometry
    out: dict[str, float] = {}
    for machine in _real_geometry.GEOMETRY.values():
        for s in machine["sensors"]:
            out[s["name"]] = float(s["theta"])
    return out


@lru_cache(maxsize=16)
def _stack_cached(shot, names):
    """Cached channel load for a fixed (shot, names) — HDF5 reads are the dominant
    cost and every mode node restacks the same toroidal array, so memoize the matrix.
    ``names`` is a tuple so the call is hashable; cleared by ``refresh`` on a new pull."""
    t0, d0 = h5source.load_channel(shot, names[0])
    datas = [d0] + [h5source.load_data(shot, nm) for nm in names[1:]]
    nmin = min(d.size for d in datas)
    return t0[:nmin], np.array([d[:nmin] for d in datas], dtype=float)


def _stack(shot, names):
    """Load channels, truncate to common length, return (t_ms, matrix[ch,time]).

    A toroidal/poloidal array shares one digitizer clock, so only the first
    channel's time axis is needed: read time once (the reference channel) and
    data-only for the rest, instead of materializing every channel's time vector.
    """
    return _stack_cached(str(shot), tuple(names))


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


# ── auto analysis frequency: the dominant mode at the cursor (so shapes track it) ─
def _auto_freq_khz(shot, t0_ms=None, fmin=1.0, fmax=25.0):
    """Peak-power frequency (kHz, rounded to 1 kHz for cache stability) at the cursor
    time from the cached 2-probe spectrogram — so the phase fit / mode shape follow the
    mode as the user scrubs, instead of sitting at a fixed frequency that misses it.
    Global peak when no cursor. Falls back to 5 kHz if the spectrogram is unavailable."""
    try:
        res, _probes, _dphi = _spec_result(str(shot), 0.001, 5)
    except Exception:  # noqa: BLE001
        return 5.0
    f_khz = np.asarray(res.frequency) / 1e3
    band = (f_khz >= fmin) & (f_khz <= fmax)
    if not np.any(band):
        return 5.0
    power = np.asarray(res.power, dtype=float)
    if t0_ms is None:
        col = power[:, band].mean(axis=0)
    else:
        ti = int(np.argmin(np.abs(np.asarray(res.time) * 1e3 - t0_ms)))
        col = power[ti, band]
    return round(float(f_khz[band][int(np.argmax(col))]))


# ── batched full-array STFT, computed once per (shot, array, f) and cached ─────
@lru_cache(maxsize=4)
def _array_spectrum(shot, names):
    """One full-array STFT over the 1–25 kHz band for a fixed (shot, probe set) — the
    expensive step. Every cursor position AND frequency then reads the complex array
    pattern out of this by indexing (``mode_from_spectrum``), so both scrubbing and
    mode-frequency changes are array-fast with no rebuild. ``names`` is a tuple so the
    call is hashable; cleared by ``refresh``."""
    t_ms, mat = _stack(shot, names)
    return spectral.array_shape_spectrum(mat, np.asarray(t_ms, dtype=float) * 1e-3)


# ── toroidal mode at one frequency/cursor (shared by phase_fit & mode_shape) ──
def _toroidal_arr(shot):
    """The toroidal (midplane) array for the n-fit: ONE consistent probe type, all at
    θ≈0 so the phase is a clean −nφ ramp. Prefer the fast-Mirnov dB/dt array; a "both"
    pull also brings the integrated-Bp (MPID) family and the off-midplane *poloidal*
    probes — mixing those in (different units, 90° dB/dt-vs-B offset, m·θ dependence)
    scrambles the fit, so they're excluded."""
    arr = _array_channels(shot, ("MPI_BDOT",))
    if len(arr) >= 4:
        return arr
    theta = _real_theta()                          # integrated-Bp midplane fallback
    arr = [(n, p) for n, p in _array_channels(shot, ("MPID",))
           if (th := theta.get(n)) is not None and (th < 20.0 or th > 340.0)]
    if len(arr) < 4:
        raise ValueError("not enough toroidal-array channels for a mode fit")
    return arr


def _toroidal_mode(shot, params):
    """Per-probe phase/amplitude (+1σ) across the toroidal array at one frequency,
    honoring the GUI time cursor. Returns (arr, mode, f_khz, t0_ms)."""
    t0_ms = _f(params, "time", None)              # GUI cursor (ms)
    f_khz = _f(params, "f_khz", None)             # explicit, else track the mode
    if f_khz is None:
        f_khz = _auto_freq_khz(shot, t0_ms)
    arr = _toroidal_arr(str(shot))
    phis = np.array([p for _, p in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    t0_s = (t0_ms * 1e-3) if t0_ms is not None else float(spec.time[spec.time.size // 2])
    mode = spectral.mode_from_spectrum(spec, phis, t0_s, f_khz * 1e3)
    return arr, mode, f_khz, t0_ms


# ── phase_fit: phase-vs-φ at one frequency, at the GUI time cursor ────────────
def _phase_fit(shot, params=None) -> dict:
    arr, mode, f_khz, t0_ms = _toroidal_mode(shot, params)
    fit = spectral.fit_toroidal_mode(mode)        # best-fit toroidal n + uncertainty
    # Real per-probe phase σ from the cross-spectral statistics (Bendat & Piersol),
    # replacing the GUI's previously fabricated error bars. The reference probe's σ is
    # NaN (self-reference); omit error_y there rather than emit a JSON-invalid NaN.
    perr = mode.phase_error if mode.phase_error is not None else [None] * len(arr)
    points = []
    for (nm, p), ph, e in zip(arr, mode.phase, perr):
        pt = {"x": float(p), "y": float(ph), "group": diiid.kind_of(nm)}
        if e is not None and np.isfinite(e):
            pt["error_y"] = round(float(e), 3)
        points.append(pt)
    # fitted line phase(φ) = c − n·φ (slope −n), matching the data ramp — not +n
    line = {"x": [0.0, 360.0],
            "y": [fit.intercept_deg, fit.intercept_deg - fit.n * 360.0]}
    return contracts.scatter2d(
        points, {"x": "φ (deg)", "y": "phase (deg)"}, fit=line,
        meta={"n_estimate": fit.n, "resultant": round(float(fit.resultant), 3),
              "n_confidence": round(float(fit.n_confidence), 3)
              if fit.n_confidence is not None else None,
              "phase_sigma_deg": round(float(fit.phase_sigma), 3)
              if fit.phase_sigma is not None else None,
              "f_kHz": f_khz, "t0_ms": t0_ms, "shot": str(shot),
              "note": "MODESPEC phase-at-frequency + circular n-fit; "
                      "error bars = 1σ cross-spectral phase uncertainty"})


# ── mode shape: GP-smoothed eigenmode shape (re/im) with 2σ bands + markers ───
def _shape_line(ms, x_label, meta) -> dict:
    """Build a `line` node for a GP mode shape: Re/Im smooth curves with ±2σ bands
    and the measured per-probe values as overlaid markers (cf. Olofsson fig 10)."""
    grid = ms.grid_deg.tolist()
    ang = ms.angle_deg.tolist()
    series = [
        {"name": "Re", "x": grid, "y": ms.re_mean.tolist(),
         "lower": (ms.re_mean - 2 * ms.re_sigma).tolist(),
         "upper": (ms.re_mean + 2 * ms.re_sigma).tolist(),
         "markers": {"x": ang, "y": ms.re_obs.tolist()}},
        {"name": "Im", "x": grid, "y": ms.im_mean.tolist(),
         "lower": (ms.im_mean - 2 * ms.im_sigma).tolist(),
         "upper": (ms.im_mean + 2 * ms.im_sigma).tolist(),
         "markers": {"x": ang, "y": ms.im_obs.tolist()}},
    ]
    return contracts.line(series, {"x": x_label, "y": "shape (a.u.)"}, meta=meta)


def _mode_shape(shot, params=None) -> dict:
    """Smooth *toroidal* mode shape (re/im vs φ) with a ±2σ band, via the
    periodic-kernel GP (eigspec §2.2.2), plus the measured probe markers."""
    arr, mode, f_khz, t0_ms = _toroidal_mode(shot, params)
    ms = _gp_shape(mode)
    return _shape_line(ms, "φ (deg)", {
        "f_kHz": f_khz, "t0_ms": t0_ms, "shot": str(shot), "n_probes": len(arr),
        "length_scale_rad": round(float(ms.length_scale), 3),
        "note": "GP toroidal mode shape (eigspec §2.2.2); curve ±2σ, markers = probes"})


def _poloidal_shape(shot, params=None) -> dict:
    """Smooth *poloidal* mode shape (re/im vs θ) with a ±2σ band, on the real DIII-D
    poloidal array (cf. Olofsson fig 10(b)). Needs a shot with the MPID array."""
    arr, mode, f_khz, t0_ms = _poloidal_mode(shot, params)
    ms = _gp_shape(mode)
    return _shape_line(ms, "θ (deg)", {
        "f_kHz": f_khz, "t0_ms": t0_ms, "shot": str(shot), "n_probes": len(arr),
        "length_scale_rad": round(float(ms.length_scale), 3),
        "note": "GP poloidal mode shape (eigspec §2.2.2); curve ±2σ, markers = probes"})


# ── poloidal mode at one frequency (uses real DIII-D θ for the 2D pattern) ────
def _poloidal_arr(shot):
    theta = _real_theta()
    arr = [(name, theta[name]) for name in h5source.channel_names(shot)
           if diiid.family_of(name) == "MPID" and name in theta]
    arr.sort(key=lambda nt: nt[1])
    if len(arr) < 4 or len({round(th, 1) for _, th in arr}) < 4:
        raise ValueError("not enough poloidal-array probes with real θ for a 2D pattern")
    return arr


def _toroidal_n(shot, t0_s, f_khz):
    """Best-fit toroidal n at (t0, f) from the midplane array — used to de-trend the
    poloidal phase (the poloidal probes span φ, so the nφ ramp must be removed)."""
    arr = _toroidal_arr(shot)
    phis = np.array([p for _, p in arr], dtype=float)
    spec = _array_spectrum(shot, tuple(n for n, _ in arr))
    mode = spectral.mode_from_spectrum(spec, phis, t0_s, f_khz * 1e3)
    return spectral.fit_toroidal_mode(mode).n


def _poloidal_mode(shot, params):
    """Per-probe phase/amplitude across the poloidal array vs θ. The probes span φ, so
    the toroidal nφ ramp is removed (phase += n·φ → −m·θ + const) using the toroidal n
    at the same (t0, f). Returns (arr, mode, f_khz, t0_ms)."""
    t0_ms = _f(params, "time", None)
    f_khz = _f(params, "f_khz", None)
    if f_khz is None:
        f_khz = _auto_freq_khz(shot, t0_ms)
    arr = _poloidal_arr(str(shot))
    thetas = np.array([th for _, th in arr], dtype=float)
    pphis = np.array([diiid.phi_of(n) or 0.0 for n, _ in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    t0_s = (t0_ms * 1e-3) if t0_ms is not None else float(spec.time[spec.time.size // 2])
    mode = spectral.mode_from_spectrum(spec, thetas, t0_s, f_khz * 1e3)
    mode.phase = (mode.phase + _toroidal_n(str(shot), t0_s, f_khz) * pphis) % 360.0
    return arr, mode, f_khz, t0_ms


def _gp_shape(mode):
    """GP-smoothed complex mode shape with Tier-1-seeded heteroscedastic noise."""
    z = mode_shape.shape_vector(mode.phase, mode.amplitude)
    noise = mode_shape.shape_noise(mode.amplitude, mode.phase_error, mode.amplitude_error)
    return mode_shape.gp_mode_shape(mode.toroidal_angle, z, value_noise=noise)


# ── mode_pattern: 2D (θ, φ) modal pattern from toroidal × poloidal shapes ─────
def _mode_pattern(shot, params=None) -> dict:
    """Rank-2 (θ, φ) modal pattern (eigspec eq 23) — the outer product of the GP
    toroidal and poloidal mode shapes, on real DIII-D probe geometry."""
    _, tmode, f_khz, t0_ms = _toroidal_mode(shot, params)
    _, pmode, _, _ = _poloidal_mode(shot, params)
    phi_g, th_g, pattern = mode_shape.mode_pattern_2d(_gp_shape(tmode), _gp_shape(pmode))
    zmax = float(np.nanmax(np.abs(pattern))) or 1.0
    return contracts.contour(
        phi_g.tolist(), th_g.tolist(), pattern.tolist(),
        {"x": "φ (deg)", "y": "θ (deg)", "z": "mode pattern (a.u.)"},
        zrange=[-zmax, zmax],
        meta={"f_kHz": f_khz, "t0_ms": t0_ms, "shot": str(shot),
              "note": "2D (θ,φ) modal pattern (eigspec eq 23) on real DIII-D θ geometry"})


# ── mode_track: shape coherence to a reference over time (full-array, fig 9) ──
def _mode_track(shot, params=None) -> dict:
    """Mode persistence: the full array's shape MAC-similarity to the strongest mode
    slice vs time (eigspec fig 9). A sustained value near 1 means the same spatial
    mode persists; a drop marks a mode change. Reads the cached full-array STFT."""
    f_khz = _f(params, "f_khz", None)
    if f_khz is None:
        f_khz = _auto_freq_khz(shot, None)        # global dominant (cursor-independent)
    arr = _toroidal_arr(str(shot))
    phis = np.array([p for _, p in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    tr = mode_shape.track_from_spectrum(spec, phis, f_khz * 1e3)
    vals, counts = np.unique(tr.n_by_time, return_counts=True)
    series = [{"name": "shape similarity to dominant mode",
               "x": tr.t_ms.tolist(), "y": tr.mac_to_ref.tolist()}]
    return contracts.line(
        series, {"x": "time (ms)", "y": "shape similarity (0–1)"},
        meta={"f_kHz": f_khz, "ref_t_ms": round(float(tr.ref_t_ms), 1),
              "dominant_n": int(vals[int(counts.argmax())]), "shot": str(shot),
              "n_probes": len(arr),
              "note": "1 = same spatial mode persists; drops mark mode changes (fig 9)"})


_BUILDERS = {
    "geometry": _geometry,
    "spectrogram": _spectrogram,
    "mode_number": _mode_number,
    "coherence": _coherence,
    "n_spectrum": _n_spectrum,
    "contour": _contour,
    "fit_quality": _fit_quality,
    "phase_fit": _phase_fit,
    "mode_shape": _mode_shape,
    "poloidal_shape": _poloidal_shape,
    "mode_pattern": _mode_pattern,
    "mode_track": _mode_track,
}


def build_node(shot: str, node_id: str, params: dict | None = None) -> dict:
    if node_id not in _BUILDERS:
        raise KeyError(f"unknown node {node_id!r}; "
                       f"have {', '.join(sorted(_BUILDERS))}")
    h5source.shot_file(shot)  # raises KeyError if the shot isn't available
    return _BUILDERS[node_id](shot, params)
