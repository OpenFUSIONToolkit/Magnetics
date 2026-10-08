"""Plasma-scenario helpers from global signals (Ip, Bt, …) — device-agnostic, pure."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class Flattop:
    kind: str  # "ip_flattop"
    t_start_ms: float  # first time |Ip| reaches the flattop level
    t_end_ms: float  # last time |Ip| is at the flattop level (ramp-down / quench after)
    ip_peak: float  # peak of the smoothed |Ip| (signal units)
    frac: float  # flattop level as a fraction of the peak


def ip_flattop(
    t_ms: NDArray[np.floating],
    ip: NDArray[np.floating],
    *,
    frac: float = 0.95,
    smooth_ms: float = 10.0,
) -> Flattop:
    """Plasma-current flattop: the span where the smoothed |Ip| is at least ``frac`` of
    its peak, from the first to the last such time.

    |Ip| makes the result sign-agnostic (KSTAR stores Ip negative), and a ``smooth_ms``
    moving average keeps single-sample spikes from setting the peak or the edges. Brief
    dips inside the flattop don't split it — the end is the LAST time at the level, i.e.
    where the ramp-down or quench begins, which is what an analysis cut-off wants.
    """
    t = np.asarray(t_ms, dtype=np.float64)
    a = np.abs(np.asarray(ip, dtype=np.float64))
    ok = np.isfinite(t) & np.isfinite(a)
    t, a = t[ok], a[ok]
    if t.size < 2:
        raise ValueError("Ip trace too short to find a flattop")
    dt = float(np.median(np.diff(t)))
    w = max(1, int(round(smooth_ms / dt))) if dt > 0 else 1
    s = np.convolve(a, np.ones(w) / w, mode="same") if w > 1 else a
    peak = float(s.max())
    if peak <= 0.0:
        raise ValueError("Ip is zero throughout — no flattop")
    on = np.flatnonzero(s >= frac * peak)
    return Flattop(
        kind="ip_flattop",
        t_start_ms=float(t[on[0]]),
        t_end_ms=float(t[on[-1]]),
        ip_peak=peak,
        frac=float(frac),
    )
