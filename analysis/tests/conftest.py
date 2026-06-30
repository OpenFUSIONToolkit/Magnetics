from pathlib import Path

import numpy as np
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def shot_174446():
    """50 ms snippet of DIII-D shot 174446 (two Mirnov dB/dt probes)."""
    d = np.load(FIXTURES / "174446_snippet.npz", allow_pickle=True)
    return {
        "time_s": d["time_ms"].astype(np.float64) * 1e-3,
        "sig_307": d["sig_307"].astype(np.float64),
        "sig_340": d["sig_340"].astype(np.float64),
        "phi_307": float(d["phi_307"]),
        "phi_340": float(d["phi_340"]),
        "fs": float(d["fs_hz"]),
        "shot": int(d["shot"]),
    }


@pytest.fixture()
def synthetic_n2():
    """Synthetic n=2 rotating mode at 3 kHz, two probes at 30° and 120°."""
    fs = 50_000
    duration = 0.1
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    f_mode = 3_000.0
    n = 2
    phi1, phi2 = 30.0, 63.0  # Δφ = -33°, mimics the real 307/340 pair separation
    sig1 = np.sin(2 * np.pi * f_mode * t - np.deg2rad(n * phi1))
    sig2 = np.sin(2 * np.pi * f_mode * t - np.deg2rad(n * phi2))
    return {
        "time": t,
        "sig1": sig1,
        "sig2": sig2,
        "delta_phi": phi1 - phi2,
        "fs": float(fs),
        "f_mode": f_mode,
        "n_true": n,
    }
