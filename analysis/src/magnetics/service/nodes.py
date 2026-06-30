"""Assemble GUI nodes from fetched shot data — orchestration only.

Each builder pulls real channels from the HDF5 (data/h5source), maps device
geometry (data/diiid), runs device-agnostic math (core/spectral, core/geometry),
and shapes the result with core/contracts. The web routes just call `build_node`.

Where the full SLCONTOUR/MODESPEC physics doesn't exist yet, we serve the real
underlying data with honest labels (e.g. raw δBp(φ,t) instead of a fitted φ–θ map)
rather than fake numbers.
"""
from __future__ import annotations

import numpy as np

from ..core import contracts, geometry, spectral
from ..data import diiid, h5source

T_TO_GAUSS = 1.0e4  # PTDATA integrated field is ~Tesla; show Gauss like the GUI


def machines() -> list[dict]:
    return h5source.list_shots()


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
def _geometry(shot) -> dict:
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


# ── spectrogram: real STFT of a Ḃ channel ────────────────────────────────────
def _pick_bdot(shot) -> str:
    names = h5source.channel_names(shot)
    bdot = [n for n in names if diiid.family_of(n) == "MPI_BDOT"]
    if bdot:
        return bdot[0]
    # fallback: the channel with the most samples (highest rate)
    best, best_n = None, -1
    for n in names:
        if diiid.phi_of(n) is None:
            continue
        t, _ = h5source.load_channel(shot, n)
        if t.size > best_n:
            best, best_n = n, t.size
    if best is None:
        raise ValueError("no usable channel for a spectrogram")
    return best


def _spectrogram(shot) -> dict:
    ch = _pick_bdot(shot)
    t_ms, y = h5source.load_channel(shot, ch)
    if t_ms.size < 32:
        raise ValueError(f"channel {ch} too short for a spectrogram "
                         f"({t_ms.size} samples)")
    dt_s = float(np.median(np.diff(t_ms))) / 1e3
    ts, fk, power = spectral.spectrogram(y, dt_s)
    return contracts.heatmap(
        ts.tolist(), fk.tolist(), power.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "log power"},
        discrete=False,
        meta={"channel": ch, "shot": str(shot),
              "fs_kHz": round(1e-3 / dt_s, 1)})


# ── contour: raw δBp(φ, t) over the toroidal array (fit pending) ──────────────
def _contour(shot) -> dict:
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
def _fit_quality(shot) -> dict:
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


# ── phase_fit: best-effort phase-vs-φ at one frequency ───────────────────────
def _phase_fit(shot, f0_khz: float = 5.0) -> dict:
    arr = _array_channels(shot, ("MPI_BDOT", "MPID"))
    if len(arr) < 4:
        raise ValueError("not enough toroidal-array channels for a phase fit")
    names = [n for n, _ in arr]
    phis = np.array([p for _, p in arr])
    t_ms, mat = _stack(shot, names)
    dt_s = float(np.median(np.diff(t_ms))) / 1e3
    phase = spectral.phase_at_frequency(mat, dt_s, f0_khz * 1e3)
    # unwrap vs phi for a slope (= toroidal n) estimate
    order = np.argsort(phis)
    pw = np.unwrap(np.deg2rad(phase[order]))
    n_slope, intercept = np.polyfit(phis[order], np.rad2deg(pw), 1)
    points = [{"x": float(p), "y": float(ph), "group": diiid.kind_of(nm)}
              for (nm, p), ph in zip(arr, phase)]
    fit = {"x": [0.0, 360.0],
           "y": [float(intercept), float(intercept + n_slope * 360.0)]}
    return contracts.scatter2d(
        points, {"x": "φ (deg)", "y": "phase (deg)"}, fit=fit,
        meta={"n_estimate": round(float(n_slope), 2), "f_kHz": f0_khz,
              "shot": str(shot),
              "note": "single-bin DFT phase — approximate, MODESPEC fit pending"})


_BUILDERS = {
    "geometry": _geometry,
    "spectrogram": _spectrogram,
    "contour": _contour,
    "fit_quality": _fit_quality,
    "phase_fit": _phase_fit,
}


def build_node(shot: str, node_id: str, params: dict | None = None) -> dict:
    if node_id not in _BUILDERS:
        raise KeyError(f"unknown node {node_id!r}; "
                       f"have {', '.join(sorted(_BUILDERS))}")
    h5source.shot_file(shot)  # raises KeyError if the shot isn't available
    return _BUILDERS[node_id](shot)


# ── frame-envelope compat (docs/CONTRACT.md) ────────────────────────────────
# The gui-branch frontend streams `qs_fit`/`spectrogram`/`geometry` as frames
# {type, progress, final, meta, data}. We serve a single final frame built from
# the same real nodes, so that GUI works against this backend unchanged.
def _qs_fit_data(shot) -> dict:
    contour = _contour(shot)  # raw δBp(φ,t) — real data, fit pending
    fq = _fit_quality(shot)
    kval = next((f["value"] for f in fq["fields"]
                 if str(f["label"]).startswith("condition number K")), 0)
    nch = next((f["value"] for f in fq["fields"]
                if f["label"] == "channels fetched"), 0)
    return {
        "contour": {"phi": contour["x"], "theta": contour["y"],
                    "z": contour["z"], "units": "G"},
        "sensors": contour.get("overlay", {}).get("points", []),
        "modes": [],
        "quality": {"K": kval if isinstance(kval, (int, float)) else 0.0,
                    "chi2": 0.0, "n_channels": nch, "m_max": 0},
    }


def _spectrogram_data(shot) -> dict:
    n = _spectrogram(shot)
    return {"spectrogram": {"t_ms": n["x"], "f_kHz": n["y"], "power": n["z"]}}


def _geometry_data(shot) -> dict:
    n = _geometry(shot)
    return {"sensors": n["points"]}


_RESULTS = {
    "qs_fit": _qs_fit_data,
    "spectrogram": _spectrogram_data,
    "geometry": _geometry_data,
}


def result_data(shot: str, result: str, params: dict | None = None) -> dict:
    """CONTRACT.md frame `data` for a result name (qs_fit/spectrogram/geometry)."""
    if result not in _RESULTS:
        raise KeyError(f"unknown result {result!r}; "
                       f"have {', '.join(sorted(_RESULTS))}")
    h5source.shot_file(shot)
    return _RESULTS[result](shot)
