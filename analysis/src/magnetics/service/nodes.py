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


def refresh() -> None:
    """Forget the cached HDF5 file index (call after a new fetch writes a file)."""
    h5source.refresh()


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
    """Load channels, truncate to common length, return (t_ms, matrix[ch,time])."""
    series = [h5source.load_channel(shot, nm) for nm in names]
    nmin = min(d.size for _, d in series)
    t = series[0][0][:nmin]
    mat = np.array([d[:nmin] for _, d in series], dtype=float)
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


def _spectrogram(shot) -> dict:
    (n1, phi1), (n2, phi2) = _pick_pair(shot)
    t1, s1 = h5source.load_channel(shot, n1)
    t2, s2 = h5source.load_channel(shot, n2)
    k = min(t1.size, s1.size, t2.size, s2.size)
    if k < 256:
        raise ValueError(f"channels too short for a spectrogram ({k} samples)")
    time_s = np.asarray(t1[:k], dtype=float) * 1e-3   # HDF5 time base is ms
    res = spectral.compute_spectrogram(time_s, s1[:k], s2[:k],
                                       delta_phi=float(phi2 - phi1))
    # power is [n_times, n_freqs]; heatmap z is [i_y=freq][i_x=time] → transpose.
    z = np.log10(np.maximum(np.asarray(res.power, dtype=float).T, 1e-30))
    return contracts.heatmap(
        (np.asarray(res.time) * 1e3).tolist(),        # x: time (ms)
        (np.asarray(res.frequency) / 1e3).tolist(),   # y: frequency (kHz)
        z.tolist(),
        {"x": "time (ms)", "y": "f (kHz)", "z": "log₁₀ power"},
        discrete=False,
        meta={"probes": [n1, n2], "delta_phi_deg": round(float(phi2 - phi1), 1),
              "shot": str(shot)})


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
    phis = np.array([p for _, p in arr], dtype=float)
    t_ms, mat = _stack(shot, names)               # mat[ch, time]
    mode = spectral.extract_mode_at_frequency(
        mat, phis, np.asarray(t_ms, dtype=float) * 1e-3, frequency=f0_khz * 1e3)
    fit = spectral.fit_toroidal_mode(mode)        # best-fit toroidal n
    points = [{"x": float(p), "y": float(ph), "group": diiid.kind_of(nm)}
              for (nm, p), ph in zip(arr, mode.phase)]
    line = {"x": [0.0, 360.0],
            "y": [fit.intercept_deg, fit.intercept_deg + fit.n * 360.0]}
    return contracts.scatter2d(
        points, {"x": "φ (deg)", "y": "phase (deg)"}, fit=line,
        meta={"n_estimate": fit.n, "resultant": round(float(fit.resultant), 3),
              "f_kHz": f0_khz, "shot": str(shot),
              "note": "MODESPEC phase-at-frequency + circular n-fit"})


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
