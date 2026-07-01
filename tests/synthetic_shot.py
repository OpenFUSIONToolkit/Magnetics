"""Generate a synthetic DIII-D-shaped HDF5 shot for tests — NO real tokamak data.

Real device *geometry* (channel names + φ/θ from the committed device table) is
fine to use; the signals here are fabricated deterministic rotating modes, never
measured samples. Written through the real writer
(:func:`magnetics.data.fetch.toksearch._write_h5`) so tests exercise the true
read path (``h5source`` and the SLCONTOUR ``io_data`` loader).

The shot carries:
  * the 14 ``MPI66M*D`` fast-Mirnov (dB/dt) midplane array — the rotating toroidal
    n-fit array;
  * (when ``include_qs``) the ``MPID`` integrated Bp LFS midplane array + the
    off-midplane ``MPID67A*``/``MPID67B*`` arrays, so the quasi-stationary
    ``Bp_LFS_midplane`` fit resolves and the poloidal probes span θ;
  * ``ip`` / ``bt`` / ``kappa`` plasma traces.

Signals are a superposition of two known rotating modes so the n/m fitters have a
ground truth: n=1 (with a poloidal m=1 component) at 5 kHz and n=2 at 8 kHz.
"""

from __future__ import annotations

import numpy as np

from magnetics.data import diiid, signals
from magnetics.data.fetch.toksearch import Channel, _write_h5

# Known ground-truth modes (recoverable by the fits).
_FS = 50_000.0  # Hz
_DURATION = 0.1  # s  → 5000 samples
_MODE1 = (1, 1, 5_000.0, 1.0)  # (n, m, f_Hz, amplitude)
_MODE2 = (2, 0, 8_000.0, 0.6)

#: Off-midplane integrated-Bp arrays that give the poloidal fit a θ spread.
_MPID_POLOIDAL = [
    "MPID67A022",
    "MPID67A037",
    "MPID67A052",
    "MPID67A097",
    "MPID67A157",
    "MPID67A217",
    "MPID67A277",
    "MPID67A337",
    "MPID67B022",
    "MPID67B037",
    "MPID67B052",
    "MPID67B097",
    "MPID67B157",
    "MPID67B217",
    "MPID67B277",
    "MPID67B337",
]


def _sensor_signal(t_s: np.ndarray, phi_deg: float, theta_deg: float) -> np.ndarray:
    """A fabricated δB(t) for a sensor at (φ, θ): the two ground-truth modes plus a
    small deterministic noise floor."""
    phi, theta = np.deg2rad(phi_deg), np.deg2rad(theta_deg)
    sig = np.zeros_like(t_s)
    for n, m, f, amp in (_MODE1, _MODE2):
        sig += amp * np.sin(2 * np.pi * f * t_s - n * phi - m * theta)
    rng = np.random.default_rng(int(round(phi_deg)) * 1000 + int(round(theta_deg)))
    sig += 0.02 * rng.standard_normal(t_s.size)
    return sig.astype(np.float32)


def _channels(shot: int, *, include_qs: bool) -> list[Channel]:
    n = int(_FS * _DURATION)
    t_ms = np.linspace(0.0, _DURATION * 1e3, n, endpoint=False)  # writer stores ms
    t_s = t_ms * 1e-3

    names = list(signals.GROUPS["MPI_BDOT"])  # rotating toroidal array
    if include_qs:
        names += [
            "MPID66M020",
            "MPID66M067",
            "MPID66M097",
            "MPID66M127",
            "MPID66M157",
            "MPID66M200",
            "MPID66M247",
            "MPID66M277",
            "MPID66M307",
            "MPID66M340",
        ]
        names += _MPID_POLOIDAL
    names = list(dict.fromkeys(names))  # dedup, keep order

    chans: list[Channel] = []
    for nm in names:
        phi = diiid.phi_of(nm, shot)
        if phi is None:
            continue  # not modeled at this shot → leave out (fetcher would skip it)
        theta = diiid.real_theta_of(nm, shot) or 0.0
        chans.append(Channel(nm, t_ms.copy(), _sensor_signal(t_s, phi, theta), ok=True))

    # Plasma traces (routed to the plasma Dataset / κ path; not sensor channels).
    ip = (1.0e6 * t_s / t_s[-1]).astype(np.float32)  # 0 → 1 MA ramp
    chans.append(Channel("ip", t_ms.copy(), ip, ok=True))
    chans.append(Channel("bt", t_ms.copy(), np.full(n, 2.0, np.float32), ok=True))
    chans.append(Channel("kappa", t_ms.copy(), np.full(n, 1.8, np.float32), ok=True))
    return chans


def write_synthetic_shot(path, shot: int = 990000, *, include_qs: bool = True) -> str:
    """Write a synthetic ``shot_<n>.h5`` at ``path`` and return the path (str).

    ``shot`` is ≥ 151593 so every channel resolves in the post-upgrade device era.
    ``tmin``/``tmax`` are written as the ``'*'`` whole-shot sentinel, so the QS path
    also exercises the ``_shot_window_ms`` fallback (the crash we fixed)."""
    _write_h5(
        str(path),
        shot,
        "both",
        "test",
        _channels(shot, include_qs=include_qs),
        compression="lzf",
        tmin=None,  # '*' sentinel
        tmax=None,
        stride=1,
    )
    return str(path)
