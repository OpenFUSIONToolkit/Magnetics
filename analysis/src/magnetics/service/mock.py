"""MOCK data generators — REAL sensor geometry, synthetic everything else.

The machines are clearly fake (MOCK-A / MOCK-B, never a real shot number), but:

  • SENSOR POSITIONS are REAL DIII-D geometry (see _real_geometry.py) — static,
    published layout — so the Sensors view and the contour's sensor overlay are
    genuinely correct.
  • FIELD and SPECTROGRAM VALUES are fabricated (numpy), shaped qualitatively from
    the real reduced shots so the plots look right:
        MOCK-A ← 164672 : dense, well-conditioned (K~6.7), m/n=2/1 LOCKED, ±~6.5 G
        MOCK-B ← 147131 : sparse legacy, ill-conditioned (K~21), ROTATING n=1, ±~40 G

Real *data* (not just geometry) arrives from the Data Streamers behind the same
endpoints; these generators just exercise the contract + streaming for the GUI.

Each generator returns a list of (progress, data) frames, coarse → fine.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np

from ._real_geometry import GEOMETRY
from magnetics.contract import stream_spectrogram

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def load_real_174446():
    snippet_path = FIXTURES / "174446_snippet.npz"
    d = np.load(snippet_path, allow_pickle=True)
    return {
        "time_s": d["time_ms"].astype(np.float64) * 1e-3,
        "sig_307": d["sig_307"].astype(np.float64),
        "sig_340": d["sig_340"].astype(np.float64),
        "phi_307": float(d["phi_307"]),
        "phi_340": float(d["phi_340"]),
        "fs": float(d["fs_hz"]),
        "shot": int(d["shot"]),
    }


# Per-machine qualitative profile, grounded in the real reduced shots.
_PROFILE = {
    "MOCK-A": dict(
        label="MOCK-A", note="fake · dense array · m/n=2/1 LOCKED · well-conditioned (K~7)",
        K=6.73, chi2=0.55, m_max=4, mode=(2, 1), amp_G=6.5, nch=58,
        modes=[(1, 2, 6.2, 312.0), (2, 1, 1.9, 28.0), (1, 1, 0.7, 140.0)],
        t_ms=(800, 3600), f_lock=True, n_dom=1,
    ),
    "MOCK-B": dict(
        label="MOCK-B", note="fake · sparse legacy array · ROTATING n=1 · ill-conditioned (K~21)",
        K=21.2, chi2=0.30, m_max=1, mode=(1, 1), amp_G=38.0, nch=10,
        modes=[(1, 1, 37.0, 64.0), (2, 1, 12.0, 210.0)],
        t_ms=(800, 6100), f_lock=False, n_dom=1,
    ),
}

MACHINES = [
    {"id": "MOCK-A", "label": "MOCK-A (mock)", "device": "synthetic", "note": "fake · dense array · m/n=2/1 LOCKED", "mock": True},
    {"id": "MOCK-B", "label": "MOCK-B (mock)", "device": "synthetic", "note": "fake · sparse legacy array · ROTATING n=1", "mock": True},
    {"id": "174446", "label": "DIII-D 174446 (real data)", "device": "DIII-D", "note": "REAL data · 307/340 probe pair · rotating mode", "mock": False}
]


def _profile(machine: str) -> dict:
    return _PROFILE.get(machine, _PROFILE["MOCK-A"])


def _geometry(machine: str) -> dict:
    return GEOMETRY.get(machine, GEOMETRY["MOCK-A"])


# ── geometry (Suh) — REAL positions, instant single final frame ─────────────
def geometry_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
    if machine == "174446":
        data = load_real_174446()
        return [(1.0, {
            "sensors": [
                {"name": "MPI66M307D", "phi": data["phi_307"], "theta": 0.0, "r": 2.41, "z": 0.0, "kind": "Bp", "family": "MPI66M"},
                {"name": "MPI66M340D", "phi": data["phi_340"], "theta": 0.0, "r": 2.41, "z": 0.0, "kind": "Bp", "family": "MPI66M"}
            ]
        })]
    return [(1.0, _geometry(machine))]


# ── qs_fit (Lunia) — coarse → fine contour grid, real sensor overlay ────────
def qs_fit_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
    if machine == "174446":
        return qs_fit_frames("MOCK-B", params)
    p = _profile(machine)
    m, n = p["mode"][0], p["mode"][1]   # m/n
    amp = p["amp_G"]
    overlay = [{"phi": s["phi"], "theta": s["theta"]} for s in _geometry(machine)["sensors"]]
    modes = [{"n": mn, "m": mm, "amp": ma, "phase_deg": mp} for (mn, mm, ma, mp) in p["modes"]]
    quality = {"K": p["K"], "chi2": p["chi2"], "n_channels": p["nch"], "m_max": p["m_max"]}

    resolutions = [(13, 9), (25, 17), (49, 33), (73, 49)]   # (nphi, ntheta), → real 73×49
    frames = []
    for i, (nphi, nth) in enumerate(resolutions):
        phi = np.linspace(0, 360, nphi)
        theta = np.linspace(0, 360, nth)
        P, T = np.meshgrid(np.radians(phi), np.radians(theta))
        z = amp * np.cos(n * P - m * T + 0.6) + 0.25 * amp * np.cos(n * P - (m + 1) * T)
        frames.append(((i + 1) / len(resolutions), {
            "contour": {"phi": np.round(phi, 1).tolist(), "theta": np.round(theta, 1).tolist(),
                        "z": np.round(z, 2).tolist(), "units": "G"},
            "sensors": overlay, "modes": modes, "quality": quality,
        }))
    return frames


# ── spectrogram (Burgess) — coarse → fine, mode that locks or rotates ────────
def spectrogram_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
    if machine == "174446":
        data = load_real_174446()
        t0_ms = float(params.get("time")) if "time" in params else None
        
        delta_phi = data["phi_307"] - data["phi_340"]
        signals = np.vstack([data["sig_307"], data["sig_340"]])
        toroidal_angles = np.array([data["phi_307"], data["phi_340"]])
        
        frames = []
        for f in stream_spectrogram(
            time=data["time_s"],
            sig1=data["sig_307"],
            sig2=data["sig_340"],
            delta_phi=delta_phi,
            t0_ms=t0_ms,
            signals=signals,
            toroidal_angles=toroidal_angles,
            slice_duration=0.004,  # 4ms window
        ):
            frames.append((f["progress"], f["data"]))
        return frames

    p = _profile(machine)
    rng = np.random.default_rng(abs(hash(machine)) % 2**32)
    t0, t1 = p["t_ms"]
    resolutions = [(60, 45), (120, 90), (240, 180)]   # (nt, nf), → real 360×180
    frames = []
    for i, (nt, nf) in enumerate(resolutions):
        t = np.linspace(t0, t1, nt)
        f = np.linspace(0, 45, nf)                    # kHz, matches real 0–45
        u = (t - t0) / (t1 - t0)
        if p["f_lock"]:                               # mode chirps down and locks (f→~0)
            branch = 1.0 + 11.0 * (1 - u)
            amp_t = np.clip(1.5 * (u < 0.85), 0.2, 1.5) + 0.6
        else:                                         # rotating mode, roughly steady f
            branch = 8.0 + 2.0 * np.sin(2 * np.pi * u)
            amp_t = 1.0 + 0.3 * np.sin(6 * np.pi * u)
        Z = amp_t[None, :] * np.exp(-((f[:, None] - branch[None, :]) ** 2) / (2 * 1.4 ** 2))
        Z = np.log10(Z + 1e-4)                        # → roughly -4 … +0.2, like real
        Z_dn = np.where(Z > Z.max() - 1.2, Z, -3.0)
        nmap = np.where(Z > Z.max() - 1.5, p["n_dom"], 0)
        phi = np.sort(rng.uniform(0, 360, 14))
        phase = ((p["n_dom"]) * phi + rng.normal(0, 9, phi.size) + 180) % 360 - 180
        frames.append(((i + 1) / len(resolutions), {
            "spectrogram": {"t_ms": np.round(t, 1).tolist(), "f_kHz": np.round(f, 2).tolist(),
                            "power": np.round(Z, 3).tolist()},
            "denoised_spectrogram": {"t_ms": np.round(t, 1).tolist(), "f_kHz": np.round(f, 2).tolist(),
                                     "power": np.round(Z_dn, 3).tolist()},
            "n_map": {"t_ms": np.round(t, 1).tolist(), "f_kHz": np.round(f, 2).tolist(),
                      "n": nmap.tolist()},
            "phase_fit": {"phi_deg": np.round(phi, 1).tolist(),
                          "phase_deg": np.round(phase, 1).tolist(),
                          "fit": {"phi_deg": [0, 360], "phase_deg": [-180, 180]},
                          "n": p["n_dom"], "t_ms": round((t0 + t1) / 2), "f_kHz": 8.0},
            "coherence": {"f_kHz": np.round(f, 2).tolist(),
                          "coh": np.round(np.clip(0.9 - 0.012 * f + rng.normal(0, 0.03, f.size), 0, 1), 3).tolist()},
        }))
    return frames


def phase_fit_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
    from magnetics.contract import build_phase_fit

    if machine == "174446":
        data = load_real_174446()
        t0_ms = float(params.get("time")) if "time" in params else None
        if t0_ms is None:
            t0_ms = (data["time_s"][0] + data["time_s"][-1]) * 1e3 / 2.0

        signals = np.vstack([data["sig_307"], data["sig_340"]])
        toroidal_angles = np.array([data["phi_307"], data["phi_340"]])

        pf = build_phase_fit(
            signals=signals,
            toroidal_angles=toroidal_angles,
            time=data["time_s"],
            t0_ms=t0_ms,
        )

        points = []
        for i, (phi, phase) in enumerate(zip(pf["phi_deg"], pf["phase_deg"])):
            points.append({
                "x": phi,
                "y": phase,
                "label": f"Probe {i+1}",
                "group": "Bp",
            })

        return [(1.0, {
            "kind": "scatter2d",
            "points": points,
            "fit": {
                "x": pf["fit"]["phi_deg"],
                "y": pf["fit"]["phase_deg"]
            },
            "axes": {
                "x": "φ (deg)",
                "y": "phase (deg)"
            },
            "meta": {
                "n_fit": pf["n"],
                "resultant": pf["resultant"],
                "f_kHz": pf["f_kHz"]
            }
        })]

    # Fallback to mock generated data
    p = _profile(machine)
    rng = np.random.default_rng(abs(hash(machine)) % 2**32)
    phi = np.sort(rng.uniform(0, 360, 14))
    phase = ((p["n_dom"]) * phi + rng.normal(0, 9, phi.size) + 180) % 360 - 180
    points = []
    for i, (ph, phs) in enumerate(zip(phi, phase)):
        points.append({
            "x": float(ph),
            "y": float(phs),
            "label": f"Probe {i+1}",
            "group": "Bp",
        })
    return [(1.0, {
        "kind": "scatter2d",
        "points": points,
        "fit": {
            "x": [0.0, 360.0],
            "y": [float((-p["n_dom"] * 0 + 180) % 360 - 180), float((-p["n_dom"] * 360 + 180) % 360 - 180)]
        },
        "axes": {
            "x": "φ (deg)",
            "y": "phase (deg)"
        },
        "meta": {
            "n_fit": p["n_dom"],
            "f_kHz": 8.0
        }
    })]


GENERATORS = {
    "geometry": geometry_frames,
    "qs_fit": qs_fit_frames,
    "spectrogram": spectrogram_frames,
    "phase_fit": phase_fit_frames,
}
