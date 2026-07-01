"""Assemble GUI nodes from fetched shot data — orchestration only.

Each builder pulls real channels from the HDF5 (data/h5source), maps device
geometry (data/diiid), runs device-agnostic math (core/spectral, core/geometry),
and shapes the result with core/contracts. The web routes just call `build_node`.

Where the full SLCONTOUR/MODESPEC physics doesn't exist yet, we serve the real
underlying data with honest labels (e.g. raw δBp(φ,t) instead of a fitted φ–θ map)
rather than fake numbers.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from functools import lru_cache

import numpy as np

from ..core import contracts, geometry, mode_shape, qs_bridge, spectral
from ..data import diiid, h5source

logger = logging.getLogger(__name__)

T_TO_GAUSS = 1.0e4  # PTDATA integrated field is ~Tesla; show Gauss like the GUI


# ── GUI param parsing (HTTP query params arrive as strings) ──────────────────
def _f(params, key, default=None):
    if not params or params.get(key) in (None, ""):
        return default
    try:
        return float(params[key])
    except TypeError, ValueError:
        return default


def _i(params, key, default=None):
    v = _f(params, key, None)
    return int(v) if v is not None else default


def _flag(params, key) -> bool:
    return bool(params) and str(params.get(key, "")).lower() in ("1", "true", "yes", "on")


def machines() -> list[dict]:
    return h5source.list_shots()


def channel_usage(shot: str) -> dict:
    """Which fetched pointnames each analysis actually consumes, and which sit idle.

    A diagnostic for trimming the data pull: any ``unused`` pointname can be dropped
    from the fetch to speed it up without changing a single plot. Roles are derived
    from the *same* selectors the nodes use (``_pick_pair`` / ``_toroidal_arr`` /
    ``_poloidal_arr``), so this can't drift from what's really wired."""
    h5source.shot_file(shot)  # KeyError if the shot isn't available
    all_names = list(h5source.channel_names(shot))
    roles: dict[str, list[str]] = {}

    def tag(names, role):
        for nm in names:
            roles.setdefault(nm, []).append(role)

    try:
        (n1, _), (n2, _) = _pick_pair(shot)
        tag([n1, n2], "2-point spectrogram")
    except ValueError:
        pass
    try:
        tag([n for n, _ in _toroidal_arr(str(shot))], "toroidal n-fit array")
    except ValueError:
        pass
    try:
        tag([n for n, _ in _poloidal_arr(str(shot))], "poloidal array")
    except ValueError:
        pass

    used = [{"name": nm, "roles": roles[nm]} for nm in all_names if nm in roles]
    unused = [nm for nm in all_names if nm not in roles]
    return {
        "shot": str(shot),
        "n_total": len(all_names),
        "n_used": len(used),
        "used": used,
        "unused": unused,
    }


def refresh() -> None:
    """Forget cached state (call after a new fetch writes a file)."""
    h5source.refresh()
    for fn in (_spec_result, _stack_cached, _array_spectrum, _array_mode_spec, _qs_run):
        fn.cache_clear()


def _array_channels(shot, families: tuple[str, ...]):
    """Channels present in this shot belonging to `families`, with a parseable
    phi, sorted by phi. Returns list of (name, phi)."""
    fam_set = set(families)
    out = []
    for name in h5source.channel_names(shot):
        if diiid.family_of(name) in fam_set:
            phi = diiid.phi_of(name, shot)
            if phi is not None:
                out.append((name, phi))
    out.sort(key=lambda np_: np_[1])
    return out


@lru_cache(maxsize=8)
def _real_theta(shot) -> dict:
    """name → real poloidal angle θ (deg), derived from the device file's
    shot-correct (r, z) about the machine axis. Only channels with genuine table
    geometry at this shot appear, so callers can still select 'probes that have a
    physical θ' (vs ``diiid``'s cosmetic per-array offset)."""
    out: dict[str, float] = {}
    for name in h5source.channel_names(shot):
        th = diiid.real_theta_of(name, shot)
        if th is not None:
            out[name] = th
    return out


def _kappa_at(shot, t0_ms=None):
    """Plasma elongation κ at the cursor time (or the shot median), from the fetched
    ``kappa`` EFIT channel. None when the pull didn't include it — the poloidal map
    then falls back to the geometric angle. κ outside a sane [1, 4] band is rejected
    as a bad EFIT sample."""
    try:
        if "kappa" not in h5source.channel_names(shot):
            return None
        t, d = h5source.load_channel(shot, "kappa")
    except KeyError, OSError:
        return None
    d = np.asarray(d, dtype=float)
    good = np.isfinite(d)
    if not np.any(good):
        return None
    if t0_ms is None:
        k = float(np.median(d[good]))
    else:
        k = float(np.interp(t0_ms, np.asarray(t, dtype=float)[good], d[good]))
    return k if 1.0 <= k <= 4.0 else None


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
        s = diiid.sensor(name, shot)
        if s["phi"] is None:
            continue
        points.append({"x": s["phi"], "y": s["theta"], "label": s["family"], "group": s["family"]})
    if not points:
        raise ValueError("no sensors with a parseable toroidal angle")
    return contracts.scatter2d(
        points,
        {"x": "φ (deg)", "y": "θ (deg)"},
        meta={
            "n_sensors": len(points),
            "shot": str(shot),
            "note": "φ, θ from the device geometry table at this shot (θ derived from r, z)",
        },
    )


# ── spectrogram: real 2-point MODESPEC cross-spectrogram ─────────────────────
def _pick_pair(shot) -> tuple[tuple[str, float], tuple[str, float]]:
    """Two toroidally-separated probes for the 2-point cross-spectrogram.
    Prefer the fast Mirnov dB/dt array (MPI_BDOT), then integrated Bp (MPID).
    Returns ((name1, phi1), (name2, phi2)) with the widest non-zero separation."""
    for families in (("MPI_BDOT",), ("MPID",), ("MPI_BDOT", "MPID", "MPIF")):
        arr = _array_channels(shot, families)  # (name, phi), sorted by phi
        if len(arr) >= 2 and arr[0][1] != arr[-1][1]:
            return arr[0], arr[-1]
    raise ValueError("need two toroidally-separated probes for a spectrogram")


@lru_cache(maxsize=8)
def _spec_result(shot: str, slice_duration: float, coherence_smooth: int, max_columns: int = 4000):
    """The (expensive) STFT, cached so the spectrogram/n-map/coherence/n-spectrum
    nodes share one compute. Keyed on the STFT-shaping params only; cheap post-ops
    (freq crop, denoise) are applied per node. Returns (result, probes, delta_phi).

    ``slice_duration`` sets the frequency resolution (df = 1/slice_duration) and
    ``max_columns`` the time-column cap (decimation lever) — the two knobs that
    trade off spectrogram sharpness against compute."""
    (n1, phi1), (n2, phi2) = _pick_pair(shot)
    t1, s1 = h5source.load_channel(shot, n1)
    t2, s2 = h5source.load_channel(shot, n2)
    k = min(t1.size, s1.size, t2.size, s2.size)
    if k < 256:
        raise ValueError(f"channels too short for a spectrogram ({k} samples)")
    time_s = np.asarray(t1[:k], dtype=float) * 1e-3  # HDF5 time base is ms
    res = spectral.compute_spectrogram(
        time_s,
        s1[:k],
        s2[:k],
        delta_phi=float(phi2 - phi1),
        slice_duration=slice_duration,
        coherence_smooth=coherence_smooth,
        max_columns=max_columns,
    )
    return res, (n1, n2), round(float(phi2 - phi1), 1)


def _prep_spec(shot, params):
    """Resolve params → a (possibly denoised) SpectrogramResult + a frequency mask.
    Shared by all spectrogram-derived nodes so a knob change re-runs the core."""
    sd = _f(params, "slice_duration", 0.001)
    cs = _i(params, "coherence_smooth", None)
    if cs is None:
        cs = _i(params, "smoothing", 5)
    mc = _i(params, "max_columns", 4000)
    res, probes, dphi = _spec_result(str(shot), sd, max(2, cs), max(2, mc))
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
        (np.asarray(res.time) * 1e3).tolist(),
        f.tolist(),
        z.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "log<sub>10</sub> power"},
        discrete=False,
        meta={"probes": list(probes), "delta_phi_deg": dphi, "shot": str(shot)},
    )


def _mode_number_2pt(shot, params=None) -> dict:
    """2-point toroidal mode number n(t,f) = round(Δφ_phase / Δφ). Alias-limited to
    |n| ≲ 180/Δφ by the probe separation; used only as a fallback when a shot lacks a
    usable multi-probe toroidal array."""
    res, mask, probes, dphi = _prep_spec(shot, params)
    f = np.asarray(res.frequency)[mask] / 1e3
    n = np.abs(np.asarray(res.mode_number, dtype=float)[:, mask])  # |n|, 0…6
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(),
        f.tolist(),
        n.T.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "toroidal |n|"},
        discrete=True,
        zrange=[-0.5, 6.5],
        meta={
            "probes": list(probes),
            "delta_phi_deg": dphi,
            "shot": str(shot),
            "method": "2-point round(phase/Δφ)",
        },
    )


def _mode_number(shot, params=None) -> dict:
    """Array-resolved toroidal mode number n(t,f): a multi-probe fit per (t,f) cell
    (exp(-inφ) projection over the whole toroidal array), so it recovers the |n| ≥ 2
    modes that the 2-point round(phase/Δφ) aliases away on a wide probe pair. Cells are
    shown only where the fit is clean (mode-coherence ≥ gate) and there is real array
    power; the rest are blanked. Falls back to the 2-point estimate for shots with no
    usable toroidal array.

    Two knobs control the blanking, both separate from the spectrogram's coherence
    slider so the n-map stays clean regardless of the power view's gate: ``n_gate``
    (mode-coherence, default 0.65) hides cells whose fit isn't a clean single-n, and
    ``n_amp_pct`` (amplitude percentile, default 80) keeps only the strongest cells —
    lower it to reveal weaker/broadband modes, raise it to show only the dominant one."""
    try:
        arr = _toroidal_arr(str(shot))
    except ValueError:
        return _mode_number_2pt(shot, params)
    names = tuple(n for n, _ in arr)
    phis = tuple(float(p) for _, p in arr)
    sd = _f(params, "slice_duration", 0.002)  # honor the resolution knob (500 Hz default)
    ms = _array_mode_spec(str(shot), names, phis, sd)

    f_khz = np.asarray(ms.freq_band) / 1e3
    mask = np.ones(f_khz.size, dtype=bool)
    fmin, fmax = _f(params, "fmin"), _f(params, "fmax")
    if fmin is not None:
        mask &= f_khz >= fmin
    if fmax is not None:
        mask &= f_khz <= fmax

    # The array STFT keeps a fine native hop; decimate time columns for the display.
    t_ms = np.asarray(ms.time) * 1e3
    ti = np.linspace(0, t_ms.size - 1, min(t_ms.size, 1500)).astype(int)

    n = np.asarray(ms.mode_number)[np.ix_(ti, mask)].astype(float)
    q = np.asarray(ms.quality)[np.ix_(ti, mask)]
    amp = np.asarray(ms.amplitude)[np.ix_(ti, mask)]

    gate = _f(params, "n_gate", 0.65)
    amp_pct = min(100.0, max(0.0, _f(params, "n_amp_pct", 80.0)))
    floor = float(np.percentile(amp, amp_pct)) if amp.size else 0.0
    show = (q >= gate) & (amp >= floor)
    # Display magnitude |n| (0…6) — folds co/counter-rotating into one label so the
    # discrete palette stays visually distinct; signed n is in the phase fit.
    z = np.where(show, np.abs(n), np.nan).T  # [freq, time]; NaN → null (Plotly gap)
    zlist = [[None if not np.isfinite(v) else float(v) for v in row] for row in z]

    return contracts.heatmap(
        t_ms[ti].tolist(),
        f_khz[mask].tolist(),
        zlist,
        {"x": "time (ms)", "y": "f (kHz)", "z": "toroidal |n|"},
        discrete=True,
        zrange=[-0.5, 6.5],  # 7-bin |n| palette aligned to integers
        meta={
            "probes": list(names),
            "n_probes": len(names),
            "shot": str(shot),
            "method": f"array projection |n|≤5 ({len(names)} probes)",
            "n_gate": round(float(gate), 2),
            "n_amp_pct": round(amp_pct, 1),
        },
    )


def _coherence(shot, params=None) -> dict:
    """Real 2-point coherence γ²(t,f) in [0,1] from the core."""
    res, mask, probes, _dphi = _prep_spec(shot, params)
    f = np.asarray(res.frequency)[mask] / 1e3
    coh = np.asarray(res.coherence, dtype=float)[:, mask]
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(),
        f.tolist(),
        coh.T.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "coherence"},
        discrete=False,
        zrange=[0.0, 1.0],
        meta={"probes": list(probes), "shot": str(shot)},
    )


def _n_spectrum(shot, params=None) -> dict:
    """RMS amplitude per toroidal mode number vs time (the n-spectrum)."""
    res, _mask, probes, _dphi = _prep_spec(shot, params)
    rms = np.asarray(res.rms_by_mode, dtype=float)  # [n_times, n_modes]
    modes = np.asarray(res.mode_indices)  # [n_modes]
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(),
        modes.tolist(),
        rms.T.tolist(),
        {"x": "time (ms)", "y": "toroidal n", "z": "rms amplitude"},
        discrete=False,
        meta={"probes": list(probes), "shot": str(shot)},
    )


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
    overlay = {"points": [{"x": float(p), "y": float(t_sub[0])} for p in phis], "symbol": "square"}
    return contracts.contour(
        phi_grid.tolist(),
        t_sub.tolist(),
        z.tolist(),
        {"x": "φ (deg)", "y": "time (ms)", "z": "δBp (G)"},
        zrange=[-zmax, zmax],
        overlay=overlay,
        meta={
            "channels": n_ch,
            "shot": str(shot),
            "note": "raw toroidal δBp(φ,t) — SLCONTOUR φ–θ fit pending",
        },
    )


# ── array wave-stripes: raw δBp(angle, t) over a few mode periods at the cursor ─
def _stripes(shot, arr, t0_ms, f_khz, *, n_cycles=8, n_time=320, n_angle=120):
    """δBp interpolated onto a regular angle×time grid over a short window around the
    cursor (≈``n_cycles`` mode periods), so a rotating mode reads as diagonal stripes.
    ``arr`` is a list of (name, angle_deg); returns (t_ms, angle_grid, z[angle, time])."""
    names = [n for n, _ in arr]
    angles = np.array([a for _, a in arr], dtype=float)
    t_ms, mat = _stack(str(shot), names)  # [ch, time], shared clock
    t_ms = np.asarray(t_ms, dtype=float)
    if t0_ms is None:
        t0_ms = float(t_ms[t_ms.size // 2])
    half = max(0.3, 0.5 * n_cycles / max(float(f_khz), 0.5))  # ms, ≈n_cycles wide
    sel = np.flatnonzero((t_ms >= t0_ms - half) & (t_ms <= t0_ms + half))
    if sel.size < 4:  # cursor off-record → centre window
        c = t_ms.size // 2
        sel = np.arange(max(0, c - 160), min(t_ms.size, c + 160))
    ti = sel[np.linspace(0, sel.size - 1, min(sel.size, n_time)).astype(int)]
    t_sub = t_ms[ti]
    vals = mat[:, ti]  # [ch, n_time]
    order = np.argsort(angles)
    ang_grid = np.linspace(0.0, 360.0, n_angle)
    ae = np.concatenate([angles[order], angles[order][:1] + 360.0])  # periodic wrap
    z = np.empty((n_angle, t_sub.size))
    for j in range(t_sub.size):
        ve = np.concatenate([vals[order, j], vals[order, j][:1]])
        z[:, j] = np.interp(ang_grid, ae, ve)
    return t_sub, ang_grid, z


def _toroidal_stripes(shot, params=None) -> dict:
    """Toroidal array waves: raw δBp(φ, t) over a few mode periods at the cursor."""
    t0_ms = _f(params, "time", None)
    f_khz = _f(params, "f_khz", None) or _auto_freq_khz(shot, t0_ms)
    arr = _toroidal_arr(str(shot))
    t_sub, ang, z = _stripes(shot, arr, t0_ms, f_khz)
    return contracts.heatmap(
        t_sub.tolist(),
        ang.tolist(),
        z.tolist(),
        {"x": "time (ms)", "y": "φ (deg)", "z": "δBp (a.u.)"},
        discrete=False,
        meta={
            "n_probes": len(arr),
            "f_kHz": round(float(f_khz), 1),
            "t0_ms": t0_ms,
            "shot": str(shot),
            "note": "raw toroidal δBp(φ,t) at the cursor; diagonal stripes = a rotating mode",
        },
    )


def _poloidal_stripes(shot, params=None) -> dict:
    """Poloidal array waves: raw δBp(θ, t) over a few mode periods at the cursor. The
    probes span φ as well as θ, so the toroidal phase is mixed in — this is the raw
    array view, not the φ-detrended poloidal fit."""
    t0_ms = _f(params, "time", None)
    f_khz = _f(params, "f_khz", None) or _auto_freq_khz(shot, t0_ms)
    arr = _poloidal_arr(str(shot))
    t_sub, ang, z = _stripes(shot, arr, t0_ms, f_khz)
    return contracts.heatmap(
        t_sub.tolist(),
        ang.tolist(),
        z.tolist(),
        {"x": "time (ms)", "y": "θ (deg)", "z": "δBp (a.u.)"},
        discrete=False,
        meta={
            "n_probes": len(arr),
            "f_kHz": round(float(f_khz), 1),
            "t0_ms": t0_ms,
            "shot": str(shot),
            "note": "raw poloidal δBp(θ,t) at the cursor (toroidal phase not removed)",
        },
    )


# ── raw_trace: one Mirnov probe's dB/dt time series at the cursor ─────────────
def _raw_trace(shot, params=None) -> dict:
    """One toroidal probe's raw dB/dt vs time over a short window around the cursor —
    the rawest view of the signal the spectrogram is built from."""
    t0_ms = _f(params, "time", None)
    half_ms = _f(params, "half_ms", 2.0)
    arr = _toroidal_arr(str(shot))
    name = arr[0][0]
    t_ms, d = h5source.load_channel(str(shot), name)
    t_ms = np.asarray(t_ms, dtype=float)
    d = np.asarray(d, dtype=float)
    if t0_ms is None:
        t0_ms = float(t_ms[t_ms.size // 2])
    sel = np.flatnonzero((t_ms >= t0_ms - half_ms) & (t_ms <= t0_ms + half_ms))
    if sel.size < 2:  # cursor off-record → centre window
        c = t_ms.size // 2
        sel = np.arange(max(0, c - 2000), min(t_ms.size, c + 2000))
    if sel.size > 2000:  # keep the line light
        sel = sel[np.linspace(0, sel.size - 1, 2000).astype(int)]
    series = [{"name": name, "x": t_ms[sel].tolist(), "y": d[sel].tolist()}]
    return contracts.line(
        series,
        {"x": "time (ms)", "y": "dB/dt (a.u.)"},
        meta={
            "probe": name,
            "t0_ms": t0_ms,
            "window_ms": round(2 * half_ms, 1),
            "shot": str(shot),
            "note": f"raw dB/dt of {name} around the cursor",
        },
    )


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
    fields = [
        {"label": "shot", "value": str(m["shot"])},
        {"label": "channels fetched", "value": m["n_channels"]},
    ]
    if len(arr) >= 7:
        phis = [p for _, p in arr]
        k = geometry.condition_number(phis, n_max=3)
        fields.insert(
            0,
            {
                "label": "condition number K (n≤3)",
                "value": round(k, 2),
                "status": contracts.quality_for_k(k),
            },
        )
        fields.append({"label": "toroidal-array channels", "value": len(arr)})
    else:
        fields.append(
            {"label": "condition number K", "value": "n/a (no toroidal array in this pull)"}
        )
    return contracts.metrics(
        "Fit quality", fields, meta={"note": "geometry-only K; full fit unavailable"}
    )


# ── auto analysis frequency: the dominant mode at the cursor (so shapes track it) ─
def _auto_freq_khz(shot, t0_ms=None, fmin=1.0, fmax=25.0):
    """Peak-power frequency (kHz, rounded to 1 kHz for cache stability) at the cursor
    time from the cached 2-probe spectrogram — so the phase fit / mode shape follow the
    mode as the user scrubs, instead of sitting at a fixed frequency that misses it.
    Global peak when no cursor. Falls back to 5 kHz if the spectrogram is unavailable."""
    try:
        res, _probes, _dphi = _spec_result(str(shot), 0.001, 5)
    except Exception:  # noqa: BLE001
        logger.warning(
            "auto-freq: spectrogram unavailable for shot %s, using 5 kHz", shot, exc_info=True
        )
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
    call is hashable; cleared by ``refresh``.

    Each entry is the full complex64 STFT (~100 MB/shot); ``maxsize`` is the deliberate
    speed-for-memory cap — raise it only with that resident cost in mind."""
    t_ms, mat = _stack(shot, names)
    return spectral.array_shape_spectrum(mat, np.asarray(t_ms, dtype=float) * 1e-3)


@lru_cache(maxsize=2)
def _array_mode_spec(shot, names, phis, slice_duration):
    """Toroidal-|n|-resolved spectrogram from a *dedicated* full-array STFT computed at
    the requested frequency resolution over a fixed 0–50 kHz band — so the n-map refines
    with the resolution knob and spans the same band as the power view, rather than being
    locked to the cursor-analysis spectrum's 1–25 kHz / 1 kHz grid.

    Heavier than reusing ``_array_spectrum`` (its own 14-probe STFT), so ``maxsize`` is
    small and only the resolution changes it — band cropping is a cheap post-op in the
    node. ``names``/``phis`` are tuples so the call is hashable; cleared by ``refresh``."""
    t_ms, mat = _stack(shot, names)
    # Cap STFT columns at ~2000: the node decimates the display to 1500 anyway, so the
    # native fine hop would just inflate the per-cell projection (an (n, t, f) einsum)
    # with columns we'd throw away.
    spec = spectral.array_shape_spectrum(
        mat,
        np.asarray(t_ms, dtype=float) * 1e-3,
        fmin=0.0,
        fmax=50_000.0,
        slice_duration=slice_duration,
        max_columns=2000,
    )
    return spectral.array_mode_spectrogram(spec, np.asarray(phis, dtype=float), n_max=5)


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
    theta = _real_theta(shot)  # integrated-Bp midplane fallback
    arr = [
        (n, p)
        for n, p in _array_channels(shot, ("MPID",))
        if (th := theta.get(n)) is not None and (th < 20.0 or th > 340.0)
    ]
    if len(arr) < 4:
        raise ValueError("not enough toroidal-array channels for a mode fit")
    return arr


def _toroidal_mode(shot, params):
    """Per-probe phase/amplitude (+1σ) across the toroidal array at one frequency,
    honoring the GUI time cursor. Returns (arr, mode, f_khz, t0_ms)."""
    t0_ms = _f(params, "time", None)  # GUI cursor (ms)
    f_khz = _f(params, "f_khz", None)  # explicit, else track the mode
    if f_khz is None:
        f_khz = _auto_freq_khz(shot, t0_ms)
    arr = _toroidal_arr(str(shot))
    phis = np.array([p for _, p in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    t0_s = (t0_ms * 1e-3) if t0_ms is not None else float(spec.time[spec.time.size // 2])
    mode = spectral.mode_from_spectrum(spec, phis, t0_s, f_khz * 1e3)
    return arr, mode, f_khz, t0_ms


# ── phase_fit: phase-vs-φ at one frequency, at the GUI time cursor ────────────
def _wrapped_ramp(intercept_deg, slope_n) -> dict:
    """Fitted line phase(a) = (c − n·a) mod 360 over a∈[0,360], WRAPPED so it traces
    the same |n| sawteeth as the (wrapped) data instead of one line shooting off-axis.
    A null break is inserted at each 0/360 wrap so the polyline doesn't draw a vertical
    jump across the panel."""
    a = np.linspace(0.0, 360.0, 361)
    y = (intercept_deg - slope_n * a) % 360.0
    fx: list = []
    fy: list = []
    prev = None
    for x, yy in zip(a, y):
        if prev is not None and abs(yy - prev) > 180.0:
            fx.append(None)
            fy.append(None)
        fx.append(round(float(x), 1))
        fy.append(round(float(yy), 1))
        prev = yy
    return {"x": fx, "y": fy}


def _phase_fit(shot, params=None) -> dict:
    arr, mode, f_khz, t0_ms = _toroidal_mode(shot, params)
    fit = spectral.fit_toroidal_mode(mode)  # best-fit toroidal n + uncertainty
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
    line = _wrapped_ramp(fit.intercept_deg, fit.n)
    return contracts.scatter2d(
        points,
        {"x": "φ (deg)", "y": "phase (deg)"},
        fit=line,
        meta={
            "n_estimate": fit.n,
            "resultant": round(float(fit.resultant), 3),
            "n_confidence": round(float(fit.n_confidence), 3)
            if fit.n_confidence is not None
            else None,
            "phase_sigma_deg": round(float(fit.phase_sigma), 3)
            if fit.phase_sigma is not None
            else None,
            "f_kHz": f_khz,
            "t0_ms": t0_ms,
            "shot": str(shot),
            "note": "MODESPEC phase-at-frequency + circular n-fit; "
            "error bars = 1σ cross-spectral phase uncertainty",
        },
    )


# ── mode shape: GP-smoothed eigenmode shape (re/im) with 2σ bands + markers ───
def _shape_line(ms, x_label, meta) -> dict:
    """Build a `line` node for a GP mode shape: Re/Im smooth curves with ±2σ bands
    and the measured per-probe values as overlaid markers (cf. Olofsson fig 10)."""
    grid = ms.grid_deg.tolist()
    ang = ms.angle_deg.tolist()
    series = [
        {
            "name": "Re",
            "x": grid,
            "y": ms.re_mean.tolist(),
            "lower": (ms.re_mean - 2 * ms.re_sigma).tolist(),
            "upper": (ms.re_mean + 2 * ms.re_sigma).tolist(),
            "markers": {"x": ang, "y": ms.re_obs.tolist()},
        },
        {
            "name": "Im",
            "x": grid,
            "y": ms.im_mean.tolist(),
            "lower": (ms.im_mean - 2 * ms.im_sigma).tolist(),
            "upper": (ms.im_mean + 2 * ms.im_sigma).tolist(),
            "markers": {"x": ang, "y": ms.im_obs.tolist()},
        },
    ]
    return contracts.line(series, {"x": x_label, "y": "shape (a.u.)"}, meta=meta)


def _mode_shape(shot, params=None) -> dict:
    """Smooth *toroidal* mode shape (re/im vs φ) with a ±2σ band, via the
    periodic-kernel GP (eigspec §2.2.2), plus the measured probe markers."""
    arr, mode, f_khz, t0_ms = _toroidal_mode(shot, params)
    ms = _gp_shape(mode)
    return _shape_line(
        ms,
        "φ (deg)",
        {
            "f_kHz": f_khz,
            "t0_ms": t0_ms,
            "shot": str(shot),
            "n_probes": len(arr),
            "length_scale_rad": round(float(ms.length_scale), 3),
            "note": "GP toroidal mode shape (eigspec §2.2.2); curve ±2σ, markers = probes",
        },
    )


def _poloidal_shape(shot, params=None) -> dict:
    """Smooth *poloidal* mode shape (re/im vs θ) with a ±2σ band, on the real DIII-D
    poloidal array (cf. Olofsson fig 10(b)). Needs a shot with the MPID array."""
    arr, mode, f_khz, t0_ms, kappa = _poloidal_mode(shot, params)
    ms = _gp_shape(mode)
    x_label = "θ* (deg, κ-corrected)" if kappa is not None else "θ (deg)"
    note = "GP poloidal mode shape (eigspec §2.2.2); curve ±2σ, markers = probes" + (
        f"; θ* straightened for κ={kappa:.2f}"
        if kappa is not None
        else "; geometric θ (no κ in this pull)"
    )
    return _shape_line(
        ms,
        x_label,
        {
            "f_kHz": f_khz,
            "t0_ms": t0_ms,
            "shot": str(shot),
            "n_probes": len(arr),
            "length_scale_rad": round(float(ms.length_scale), 3),
            "kappa": round(float(kappa), 3) if kappa is not None else None,
            "note": note,
        },
    )


# ── poloidal mode at one frequency (uses real DIII-D θ for the 2D pattern) ────
def _poloidal_arr(shot):
    theta = _real_theta(shot)
    arr = [
        (name, theta[name])
        for name in h5source.channel_names(shot)
        if diiid.family_of(name) == "MPID" and name in theta
    ]
    arr.sort(key=lambda nt: nt[1])
    if len(arr) < 4 or len({round(th, 1) for _, th in arr}) < 4:
        raise ValueError("not enough poloidal-array probes with real θ for a 2D pattern")
    return arr


def _theta_star(thetas_deg, kappa):
    """Geometric θ → elongation-corrected θ* when κ is known, else θ unchanged.
    Returns (angles_deg, used_star)."""
    if kappa is None:
        return np.asarray(thetas_deg, dtype=float), False
    return geometry.elongation_theta_star(thetas_deg, kappa), True


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
    at the same (t0, f). The probe angles are mapped to the elongation-corrected θ*
    (using the EFIT κ at the cursor) when available, so an `m` mode is a clean sinusoid
    rather than a κ-distorted one. Returns (arr, mode, f_khz, t0_ms, kappa)."""
    t0_ms = _f(params, "time", None)
    f_khz = _f(params, "f_khz", None)
    if f_khz is None:
        f_khz = _auto_freq_khz(shot, t0_ms)
    arr = _poloidal_arr(str(shot))
    kappa = _kappa_at(str(shot), t0_ms)
    thetas, _used = _theta_star([th for _, th in arr], kappa)
    pphis = np.array([diiid.phi_of(n, shot) or 0.0 for n, _ in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    t0_s = (t0_ms * 1e-3) if t0_ms is not None else float(spec.time[spec.time.size // 2])
    mode = spectral.mode_from_spectrum(spec, thetas, t0_s, f_khz * 1e3)
    detrended = (mode.phase + _toroidal_n(str(shot), t0_s, f_khz) * pphis) % 360.0
    mode = dataclasses.replace(mode, phase=detrended)
    return arr, mode, f_khz, t0_ms, kappa


def _poloidal_phase_fit(shot, params=None) -> dict:
    """Poloidal analogue of ``phase_fit``: per-probe phase vs θ across the poloidal
    array (φ-detrended), with the best-fit poloidal mode number m and a wrapped fit
    line. θ is the elongation-corrected θ* when the EFIT κ is in the pull."""
    arr, mode, f_khz, t0_ms, kappa = _poloidal_mode(shot, params)
    fit = spectral.fit_toroidal_mode(mode)  # same circular fit, here vs θ → m
    perr = mode.phase_error if mode.phase_error is not None else [None] * len(arr)
    th_used, _ = _theta_star([th for _, th in arr], kappa)
    points = []
    for ths, ph, e in zip(th_used, mode.phase, perr):
        pt = {"x": float(ths), "y": float(ph), "group": "Bp"}
        if e is not None and np.isfinite(e):
            pt["error_y"] = round(float(e), 3)
        points.append(pt)
    line = _wrapped_ramp(fit.intercept_deg, fit.n)
    x_label = "θ* (deg, κ-corrected)" if kappa is not None else "θ (deg)"
    return contracts.scatter2d(
        points,
        {"x": x_label, "y": "phase (deg)"},
        fit=line,
        meta={
            "m_fit": fit.n,
            "resultant": round(float(fit.resultant), 3),
            "n_confidence": round(float(fit.n_confidence), 3)
            if fit.n_confidence is not None
            else None,
            "f_kHz": f_khz,
            "t0_ms": t0_ms,
            "shot": str(shot),
            "kappa": round(float(kappa), 3) if kappa is not None else None,
            "note": "poloidal phase-at-frequency + circular m-fit (φ-detrended); "
            "error bars = 1σ cross-spectral phase uncertainty",
        },
    )


def _gp_shape(mode):
    """GP-smoothed complex mode shape with Tier-1-seeded heteroscedastic noise."""
    z = mode_shape.shape_vector(mode.phase, mode.amplitude)
    noise = mode_shape.shape_noise(mode.amplitude, mode.phase_error, mode.amplitude_error)
    return mode_shape.gp_mode_shape(mode.toroidal_angle, z, value_noise=noise)


# ── mode_pattern: 2D (θ, φ) modal pattern from toroidal × poloidal shapes ─────
def _pattern_overlay(shot, kappa=None) -> dict:
    """The real sensors that built the pattern, as (φ, θ) dots labelled by pointname:
    the poloidal array at its (φ, θ) and the toroidal array along θ≈0. The poloidal
    dots use the same elongation-corrected θ* as the pattern axis (when κ is known) so
    they land on the field they sampled. Lets the GUI show where the field is actually
    sampled (and name each probe on hover)."""
    pts = []
    try:
        arr = _poloidal_arr(str(shot))
        th_star, _ = _theta_star([th for _, th in arr], kappa)
        for (nm, _th), ths in zip(arr, th_star):
            phi = diiid.phi_of(nm, shot)
            if phi is not None:
                pts.append({"x": float(phi), "y": float(ths), "label": nm})
    except ValueError:
        pass
    try:
        for nm, phi in _toroidal_arr(str(shot)):
            pts.append({"x": float(phi), "y": 0.0, "label": nm})
    except ValueError:
        pass
    return {"points": pts, "symbol": "circle"}


def _mode_pattern(shot, params=None) -> dict:
    """Rank-2 (θ, φ) modal pattern (eigspec eq 23) — the outer product of the GP
    toroidal and poloidal mode shapes, on real DIII-D probe geometry. The poloidal
    axis is the elongation-corrected θ* when the EFIT κ is available."""
    _, tmode, f_khz, t0_ms = _toroidal_mode(shot, params)
    _, pmode, _, _, kappa = _poloidal_mode(shot, params)
    phi_g, th_g, pattern = mode_shape.mode_pattern_2d(_gp_shape(tmode), _gp_shape(pmode))
    zmax = float(np.nanmax(np.abs(pattern))) or 1.0
    y_label = "θ* (deg, κ-corrected)" if kappa is not None else "θ (deg)"
    note = (
        "2D (θ,φ) modal pattern (eigspec eq 23) on real DIII-D geometry; "
        "dots = probe locations"
        + (
            f"; θ* straightened for κ={kappa:.2f}"
            if kappa is not None
            else "; geometric θ (no κ in this pull)"
        )
    )
    return contracts.contour(
        phi_g.tolist(),
        th_g.tolist(),
        pattern.tolist(),
        {"x": "φ (deg)", "y": y_label, "z": "mode pattern (a.u.)"},
        zrange=[-zmax, zmax],
        overlay=_pattern_overlay(shot, kappa),
        meta={
            "f_kHz": f_khz,
            "t0_ms": t0_ms,
            "shot": str(shot),
            "kappa": round(float(kappa), 3) if kappa is not None else None,
            "note": note,
        },
    )


# ── mode_track: shape coherence to a reference over time (full-array, fig 9) ──
def _mode_track(shot, params=None) -> dict:
    """Mode persistence: the full array's shape MAC-similarity to the strongest mode
    slice vs time (eigspec fig 9). A sustained value near 1 means the same spatial
    mode persists; a drop marks a mode change. Reads the cached full-array STFT."""
    f_khz = _f(params, "f_khz", None)
    if f_khz is None:
        f_khz = _auto_freq_khz(shot, None)  # global dominant (cursor-independent)
    n_slices = _i(params, "n_slices", 300)
    arr = _toroidal_arr(str(shot))
    phis = np.array([p for _, p in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    # Sample finely, but only over the active-signal window — the full record is mostly
    # dead time, which both coarsens the trace and biases the dominant mode toward n=0.
    t_lo, t_hi = mode_shape.active_time_window(spec)
    tr = mode_shape.track_from_spectrum(
        spec, phis, f_khz * 1e3, n_slices=n_slices, t_range=(t_lo, t_hi)
    )
    vals, counts = np.unique(tr.n_by_time, return_counts=True)
    series = [
        {
            "name": "shape similarity to dominant mode",
            "x": tr.t_ms.tolist(),
            "y": tr.mac_to_ref.tolist(),
        }
    ]
    return contracts.line(
        series,
        {"x": "time (ms)", "y": "shape similarity (0–1)"},
        meta={
            "f_kHz": f_khz,
            "ref_t_ms": round(float(tr.ref_t_ms), 1),
            "dominant_n": int(vals[int(counts.argmax())]),
            "shot": str(shot),
            "n_probes": len(arr),
            "n_slices": int(tr.t_ms.size),
            "t_window_ms": [round(t_lo * 1e3, 1), round(t_hi * 1e3, 1)],
            "note": "1 = same spatial mode persists; drops mark mode changes (fig 9)",
        },
    )


# ── mode_over_time: dominant toroidal mode number n(t) over the shot ─────────
def _mode_over_time(shot, params=None) -> dict:
    """Best-fit toroidal mode number n vs time — the n(t) trace. Each slice fits n at
    *its own* dominant in-band frequency (``ridge_track_from_spectrum``), so the line
    follows the strongest mode as it evolves and its frequency drifts, instead of locking
    to one global bin while other simultaneous modes go unrepresented. Cursor-independent
    and restricted to the active-signal window. The full (t,f) n-map (``mode_number``)
    is the complete multi-mode view; this is its 1-D strongest-mode summary."""
    n_slices = _i(params, "n_slices", 300)
    arr = _toroidal_arr(str(shot))
    phis = np.array([p for _, p in arr], dtype=float)
    spec = _array_spectrum(str(shot), tuple(n for n, _ in arr))
    t_lo, t_hi = mode_shape.active_time_window(spec)
    tr = mode_shape.ridge_track_from_spectrum(spec, phis, n_slices=n_slices, t_range=(t_lo, t_hi))
    vals, counts = np.unique(tr.n_by_time, return_counts=True)
    f_lo, f_hi = (
        (float(np.min(tr.freq_khz)), float(np.max(tr.freq_khz))) if tr.freq_khz.size else (0.0, 0.0)
    )
    series = [
        {
            "name": "toroidal n (strongest mode)",
            "x": tr.t_ms.tolist(),
            "y": tr.n_by_time.astype(float).tolist(),
        }
    ]
    return contracts.line(
        series,
        {"x": "time (ms)", "y": "toroidal n"},
        meta={
            "dominant_n": int(vals[int(counts.argmax())]),
            "f_range_kHz": [round(f_lo, 1), round(f_hi, 1)],
            "n_probes": len(arr),
            "n_slices": int(tr.t_ms.size),
            "t_window_ms": [round(t_lo * 1e3, 1), round(t_hi * 1e3, 1)],
            "shot": str(shot),
            "note": "best-fit toroidal n of the strongest in-band mode at each time "
            "(frequency follows the ridge); see the n-map for all modes",
        },
    )


# ── quasi-stationary fit (SLCONTOUR via magnetics-code pipeline) ─────────────

_QS_RUN_LOCK = threading.Lock()


@lru_cache(maxsize=8)
def _qs_run(
    shot: str,
    ns: tuple,
    ms: tuple,
    channel_filter: str,
    detrend_type: str,
    detrend_band: tuple,
    cutoff_lo: float,
    cutoff_hi: float,
    energy: float,
    tmin_s: float,
    tmax_s: float,
):
    """Run the full SLCONTOUR pipeline (io_data → prep → fit) for one shot.

    Delegates to magnetics-code/run.run_steps. All tuning parameters are
    explicit cache-key arguments so the result is reused across node requests
    that share the same settings. tmin_s/tmax_s are in seconds and come from
    _prep_qs_ds (which reads HDF5 defaults and applies any user override).
    """
    from .._slcontour.run import run_steps

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
    channel_filter = (
        params.get("channel_filter", "Bp_LFS_midplane") if params else "Bp_LFS_midplane"
    )
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
        return _qs_run(
            str(shot),
            ns,
            ms,
            channel_filter,
            detrend_type,
            (db_lo, db_hi),
            cutoff_lo,
            cutoff_hi,
            energy,
            tmin_s,
            tmax_s,
        )


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

    from .._slcontour.omfit_compat import load_wall

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

    return contracts.line(
        series,
        {"x": "R (m)", "y": "z (m)"},
        meta={
            "wall": wall,
            "shot": str(shot),
            "channels": channels,
            "note": "sensor extent segments from device geometry",
        },
    )


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

    return contracts.line(
        series, {"x": "φ (deg)", "y": "θ (deg)"}, meta={"shot": str(shot), "channels": channels}
    )


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
    # QS (#24): sensor map + conditioning + fit-quality time series
    "sensor_map_rz": _sensor_map_rz,
    "sensor_map_cylindrical": _sensor_map_cylindrical,
    "signal_conditioning": _signal_conditioning,
    "chi_sq_t": _chi_sq_t,
    "fit_signals": _fit_signals,
    "fit_residuals": _fit_residuals,
    # rotating eigspec (develop): GP mode shapes + patterns + tracks
    "mode_shape": _mode_shape,
    "poloidal_shape": _poloidal_shape,
    "mode_pattern": _mode_pattern,
    "mode_track": _mode_track,
    "mode_over_time": _mode_over_time,
    # rotating array views: raw wave-stripes + poloidal phase fit + raw trace
    "toroidal_stripes": _toroidal_stripes,
    "poloidal_stripes": _poloidal_stripes,
    "poloidal_phase_fit": _poloidal_phase_fit,
    "raw_trace": _raw_trace,
}


def build_node(shot: str, node_id: str, params: dict | None = None) -> dict:
    if node_id not in _BUILDERS:
        raise KeyError(f"unknown node {node_id!r}; have {', '.join(sorted(_BUILDERS))}")
    h5source.shot_file(shot)  # raises KeyError if the shot isn't available
    return _BUILDERS[node_id](shot, params)
