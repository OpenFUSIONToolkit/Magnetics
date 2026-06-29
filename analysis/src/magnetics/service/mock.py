"""MOCK data generators — fabricated, clearly-fake, but qualitatively D3D-like.

NOT measured data. Every array here is synthetic (numpy), so the machines are
named MOCK-A / MOCK-B and never a real shot number. The *shapes and ranges* are
reproduced qualitatively from the real DIII-D reduced data in the demo workspace
(shots 164672 and 147131) so the GUI plots look the way real ones should:

  MOCK-A  ← dense, well-conditioned (K~6.7), m/n=2/1 LOCKED mode, contour ±~6.5 G,
            m_max 4, spectrogram branch that slows and locks.
  MOCK-B  ← sparse legacy array, ill-conditioned (K~21), ROTATING n=1, contour
            ±~40 G, m_max 1.

Real data comes from the Data Streamers behind the same endpoints; these
generators just exercise the contract + streaming for GUI development.

Each generator returns a list of (progress, data) frames, coarse → fine.
"""
from __future__ import annotations

import numpy as np

# DIII-D-like shaped surface (R0,a,kappa chosen to match real r∈[0.98,2.41],
# z∈[-1.1,1.3]); used only to give sensors plausible (r,z) for the R–Z view.
_R0, _A, _KAPPA = 1.69, 0.72, 1.8

# Per-machine qualitative profile, grounded in the real reduced shots.
_PROFILE = {
    "MOCK-A": dict(
        label="MOCK-A", note="fake · dense array · m/n=2/1 LOCKED · well-conditioned (K~7)",
        families=[("MPI66M", "LFS toroidal Mirnov", "Bp", 14, 0.0),
                  ("MPID", "Bp pairs · 2D", "Bp", 24, None),
                  ("ISLD", "Br saddle pairs · 2D", "Br", 16, None),
                  ("ICOIL", "I-coils", "coil", 4, None)],
        K=6.73, chi2=0.55, m_max=4, mode=(2, 1), amp_G=6.5,
        modes=[(1, 2, 6.2, 312.0), (2, 1, 1.9, 28.0), (1, 1, 0.7, 140.0)],
        t_ms=(800, 3600), f_lock=True, n_dom=1,
    ),
    "MOCK-B": dict(
        label="MOCK-B", note="fake · sparse legacy array · ROTATING n=1 · ill-conditioned (K~21)",
        families=[("MPI66M", "LFS toroidal Mirnov", "Bp", 6, 0.0),
                  ("MPID", "Bp pairs · 2D", "Bp", 4, None),
                  ("ISLD", "Br saddle · 2D", "Br", 2, None)],
        K=21.2, chi2=0.30, m_max=1, mode=(1, 1), amp_G=38.0,
        modes=[(1, 1, 37.0, 64.0), (2, 1, 12.0, 210.0)],
        t_ms=(800, 6100), f_lock=False, n_dom=1,
    ),
}

MACHINES = [{"id": k, "label": v["label"], "device": "synthetic",
             "note": v["note"], "mock": True} for k, v in _PROFILE.items()]


def _profile(machine: str) -> dict:
    return _PROFILE.get(machine, _PROFILE["MOCK-A"])


def _rz(theta_deg):
    t = np.radians(theta_deg)
    return _R0 + _A * np.cos(t), _KAPPA * _A * np.sin(t)


# ── geometry (Suh) — instant, single final frame ────────────────────────────
def geometry_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
    p = _profile(machine)
    rng = np.random.default_rng(abs(hash(machine)) % 2**32)
    sensors, arrays = [], []
    for fam, label, kind, count, theta0 in p["families"]:
        phis = (np.linspace(0, 360, count, endpoint=False) + rng.uniform(0, 25)) % 360
        for i, ph in enumerate(phis):
            th = 0.0 if theta0 is not None else float(rng.uniform(0, 360))
            r, z = _rz(th)
            sensors.append({"name": f"{fam}{i:02d}", "phi": round(float(ph), 1),
                            "theta": round(th, 1), "r": round(float(r), 3),
                            "z": round(float(z), 3), "kind": kind, "family": fam})
        arrays.append({"family": fam, "label": label, "kind": kind, "count": count})
    return [(1.0, {"sensors": sensors, "arrays": arrays})]


# ── qs_fit (Lunia) — coarse → fine contour grid ─────────────────────────────
def qs_fit_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
    p = _profile(machine)
    m, n = p["mode"][0], p["mode"][1]   # m/n
    amp = p["amp_G"]
    sensors = geometry_frames(machine, {})[0][1]["sensors"]
    overlay = [{"phi": s["phi"], "theta": s["theta"]} for s in sensors]
    modes = [{"n": mn, "m": mm, "amp": ma, "phase_deg": mp} for (mn, mm, ma, mp) in p["modes"]]
    quality = {"K": p["K"], "chi2": p["chi2"], "n_channels": len(sensors), "m_max": p["m_max"]}

    resolutions = [(13, 9), (25, 17), (49, 33), (73, 49)]   # (nphi, ntheta), → real 73×49
    frames = []
    for i, (nphi, nth) in enumerate(resolutions):
        phi = np.linspace(0, 360, nphi)
        theta = np.linspace(0, 360, nth)
        P, T = np.meshgrid(np.radians(phi), np.radians(theta))
        # dominant helical mode + a weak sideband, ≈ real amplitude
        z = amp * np.cos(n * P - m * T + 0.6) + 0.25 * amp * np.cos(n * P - (m + 1) * T)
        frames.append(((i + 1) / len(resolutions), {
            "contour": {"phi": np.round(phi, 1).tolist(), "theta": np.round(theta, 1).tolist(),
                        "z": np.round(z, 2).tolist(), "units": "G"},
            "sensors": overlay, "modes": modes, "quality": quality,
        }))
    return frames


# ── spectrogram (Burgess) — coarse → fine, mode that locks or rotates ────────
def spectrogram_frames(machine: str, params: dict) -> list[tuple[float, dict]]:
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
        nmap = np.where(Z > Z.max() - 1.5, p["n_dom"], 0)
        phi = np.sort(rng.uniform(0, 360, max(6, p["modes"][0][0] + 5)))
        phase = ((p["n_dom"]) * phi + rng.normal(0, 9, phi.size) + 180) % 360 - 180
        frames.append(((i + 1) / len(resolutions), {
            "spectrogram": {"t_ms": np.round(t, 1).tolist(), "f_kHz": np.round(f, 2).tolist(),
                            "power": np.round(Z, 3).tolist()},
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


GENERATORS = {
    "geometry": geometry_frames,
    "qs_fit": qs_fit_frames,
    "spectrogram": spectrogram_frames,
}
