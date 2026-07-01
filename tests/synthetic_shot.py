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

from typing import NamedTuple

import numpy as np

from magnetics.data import device_geom, devices, diiid, signals
from magnetics.data.fetch.toksearch import Channel, Profile, _write_h5, resolve_sensor_set


class _Mode(NamedTuple):
    """A ground-truth rotating mode. Named fields so consumers read ``.amp`` etc.
    rather than positional indices."""

    n: int
    m: int
    f_hz: float
    amp: float


# Known ground-truth modes (recoverable by the fits).
_FS = 50_000.0  # Hz
_DURATION = 0.1  # s  → 5000 samples
_MODE1 = _Mode(n=1, m=1, f_hz=5_000.0, amp=1.0)
_MODE2 = _Mode(n=2, m=0, f_hz=8_000.0, amp=0.6)

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

    if include_qs:
        # A synthetic EFIT02-style q-profile: monotonic q0≈1.05 → q_edge≈4.5 on a
        # uniform ψ_N grid, ~constant over a handful of coarse EFIT time slices. Gives
        # the mode-number anchor real rational surfaces (q=2 at m/n=6/3, etc.) to test
        # against — no tokamak data, just a physical shape.
        q_t = np.linspace(0.0, _DURATION * 1e3, 5)  # 5 EFIT slices (ms)
        psi = np.linspace(0.0, 1.0, 65)
        q1d = 1.05 + 3.45 * psi**2  # q(0)=1.05, q(1)=4.5
        q2d = np.tile(q1d, (q_t.size, 1)).astype(np.float32)  # [ntime, npsi], steady
        chans.append(Profile("q_profile", q_t, psi, q2d, ok=True))
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


# ── NSTX / NSTX-U synthetic shot ─────────────────────────────────────────────
#: NSTX-U shot ≥ 204718 so the post-upgrade fastmag Mirnov segments resolve.
NSTX_SHOT = 204718
#: The HN toroidal set is the rotating n-fit array (distinct φ per probe).
_NSTX_TOROIDAL_SET = "HN toroidal array"


def _nstx_channels(shot: int) -> list[Channel]:
    """Fabricated δB(t) for the NSTX HN + HF Mirnov arrays valid at ``shot``,
    plus ip/bt0/kappa. Signals are the same two ground-truth rotating modes;
    φ/θ come from the real ``nstx.json`` device table (fabricated *values*, real
    *geometry* — no measured samples)."""
    n = int(_FS * _DURATION)
    t_ms = np.linspace(0.0, _DURATION * 1e3, n, endpoint=False)
    t_s = t_ms * 1e-3

    dg = device_geom.get("nstx")
    dev = devices.load_device("nstx")
    # HN toroidal (rotating array) + HF all (adds a poloidal spread), deduped.
    names: list[str] = []
    for set_name in (_NSTX_TOROIDAL_SET, "HF all"):
        for nm in resolve_sensor_set(dev, set_name):
            if nm not in names:
                names.append(nm)

    chans: list[Channel] = []
    for nm in names:
        if not devices.valid_at(dev, nm, shot):
            continue  # NotAvailable / out-of-range at this shot → fetcher would skip
        phi = dg.phi_of(nm, shot)
        theta = dg.real_theta_of(nm, shot) or 0.0
        if phi is None:
            continue
        chans.append(Channel(nm, t_ms.copy(), _sensor_signal(t_s, phi, theta), ok=True))

    ip = (0.9e6 * t_s / t_s[-1]).astype(np.float32)  # NSTX-U-scale ramp
    chans.append(Channel("ip", t_ms.copy(), ip, ok=True))
    chans.append(Channel("bt0", t_ms.copy(), np.full(n, 1.0, np.float32), ok=True))
    chans.append(Channel("kappa", t_ms.copy(), np.full(n, 2.2, np.float32), ok=True))
    return chans


def write_synthetic_nstx_shot(path, shot: int = NSTX_SHOT) -> str:
    """Write a synthetic NSTX-U ``shot_<n>.h5`` at ``path`` (real fastmag channel
    names + ``device_id='nstx'``, fabricated signals) and return the path (str)."""
    _write_h5(
        str(path),
        shot,
        "rotating",
        "test",
        _nstx_channels(shot),
        compression="lzf",
        tmin=None,  # '*' sentinel
        tmax=None,
        stride=1,
        device="NSTX/NSTX-U",
        device_id="nstx",
    )
    return str(path)
