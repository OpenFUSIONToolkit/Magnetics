"""Shared test fixtures.

IMPORTANT: no real tokamak data lives in this repo. Every fixture below is
fabricated (synthetic rotating modes); see ``tests/synthetic_shot.py`` and the
"Test data policy" note in CLAUDE.md.
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Make sibling test helpers (synthetic_shot.py) importable regardless of pytest's
# import mode.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Point the data layer at an isolated synthetic dir BEFORE any test module (or
# the SLCONTOUR io_data loader, which freezes DATAFILE_ROOT from data_dir() at its
# import) resolves the data directory. conftest is imported before test modules,
# so setting the env here wins. This also makes the node suite deterministic —
# tests never depend on whatever real shots a dev happens to have on disk.
_SYNTH_DIR = Path(tempfile.mkdtemp(prefix="magnetics-synth-"))
os.environ["MAGNETICS_DATA_DIR"] = str(_SYNTH_DIR)
_DATAFILE = _SYNTH_DIR / "datafile"

#: Synthetic shot ids (≥ 151593 so all channels resolve in the post-upgrade era).
SYNTH_SHOT = 990000  # full rotating + quasi-stationary arrays
SYNTH_ROTATING_ONLY_SHOT = 990001  # MPI_BDOT only → QS fit has no array (422 path)
#: Synthetic NSTX-U shot (real fastmag channel names, fabricated signals).
SYNTH_NSTX_SHOT = 204718


@pytest.fixture(scope="session", autouse=True)
def _synthetic_data():
    """Write the synthetic shots once and point the caches at them."""
    from synthetic_shot import write_synthetic_nstx_shot, write_synthetic_shot

    _DATAFILE.mkdir(parents=True, exist_ok=True)
    write_synthetic_shot(_DATAFILE / f"shot_{SYNTH_SHOT}.h5", SYNTH_SHOT, include_qs=True)
    write_synthetic_shot(
        _DATAFILE / f"shot_{SYNTH_ROTATING_ONLY_SHOT}.h5",
        SYNTH_ROTATING_ONLY_SHOT,
        include_qs=False,
    )
    write_synthetic_nstx_shot(_DATAFILE / f"shot_{SYNTH_NSTX_SHOT}.h5", SYNTH_NSTX_SHOT)
    # Clear the lru_cached shot index + node compute caches so they see the files.
    from magnetics.data import h5source
    from magnetics.service import nodes

    h5source.refresh()
    nodes.refresh()
    yield


@pytest.fixture()
def synthetic_shot():
    """Id of the full synthetic shot (rotating + QS arrays)."""
    return str(SYNTH_SHOT)


@pytest.fixture()
def rotating_only_shot():
    """Id of a synthetic shot with only the rotating array (no QS Bp array)."""
    return str(SYNTH_ROTATING_ONLY_SHOT)


@pytest.fixture()
def nstx_shot():
    """Id of the synthetic NSTX-U shot (real fastmag names, fabricated signals)."""
    return str(SYNTH_NSTX_SHOT)


@pytest.fixture()
def shot_174446():
    """Synthetic stand-in for the old shot-174446 two-probe snippet.

    Formerly a committed 50 ms slice of real DIII-D data; replaced with a
    fabricated n=2 mode so no real samples live in the repo. Same keys/shape as
    before so the spectral tests read it unchanged."""
    fs = 200_000.0
    duration = 0.05
    t = np.arange(0.0, duration, 1.0 / fs)
    f_mode, n = 8_000.0, 2
    phi_307, phi_340 = 307.0, 340.0
    # A strong coherent mode BURST (present ~30% of the record) plus independent
    # per-probe noise. Mimics real data: the burst beats the denoiser's
    # per-frequency power floor (a stationary tone would not) and is coherent, so
    # it survives; the incoherent broadband noise is removed.
    rng = np.random.default_rng(174446)
    burst = ((t >= 0.40 * duration) & (t <= 0.70 * duration)).astype(float)
    mode_307 = burst * np.sin(2 * np.pi * f_mode * t - np.deg2rad(n * phi_307))
    mode_340 = burst * np.sin(2 * np.pi * f_mode * t - np.deg2rad(n * phi_340))
    sig_307 = mode_307 + 0.05 * rng.standard_normal(t.size)
    sig_340 = mode_340 + 0.05 * rng.standard_normal(t.size)
    return {
        "time_s": t,
        "sig_307": sig_307,
        "sig_340": sig_340,
        "phi_307": phi_307,
        "phi_340": phi_340,
        "fs": fs,
        "shot": 174446,
    }


@pytest.fixture()
def synthetic_n2():
    """Synthetic n=2 rotating mode at 3 kHz, two probes at 30° and 63°."""
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
