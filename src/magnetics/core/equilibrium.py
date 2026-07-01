"""q-profile physics: rational surfaces and mode-number anchoring.

A magnetic island / tearing mode lives on a *rational* flux surface where the
safety factor q = m/n is a ratio of the poloidal (m) and toroidal (n) mode numbers.
The toroidal n from a well-sampled toroidal array is reliable; the poloidal m from a
sparse, unevenly-sampled poloidal array is easily *aliased* (a physical m folds down
to a spurious small one). The q-profile breaks that degeneracy: for the measured n,
only integer m with a real q = m/n surface in the plasma (q_min ≤ m/n ≤ q_max) are
physically possible, so an aliased m/n below q_min (e.g. m/n = 1/3, q ≈ 0.33, inside
the q ≈ 1 axis) can be rejected and replaced by the physical alias.

Pure numpy over arrays: no device specifics, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class RationalSurface:
    m: int  # poloidal mode number of the resonance
    n: int  # toroidal mode number (the anchor)
    q: float  # q = m/n at the surface
    psi_n: float  # normalized flux ψ_N of the (outermost) crossing, in [0, 1]


@dataclass(slots=True)
class MAnchorResult:
    chosen_m: int  # physically-anchored poloidal mode number (signed, MAC's sign kept)
    q_surface: float | None  # q = |chosen_m|/|n| if it resonates, else None
    psi_n: float | None  # ψ_N of the resonant surface, if any
    corrected: bool  # True if the raw MAC winner was unphysical and got replaced
    raw_m: int  # the raw MAC-argmax m, before the q-anchor
    allowed_ms: list[int]  # |m| that have a q = m/n surface (within the MAC alias set)
    q_min: float
    q_max: float


def _crossings(psi_n: NDArray[np.floating], q: NDArray[np.floating], target: float) -> list[float]:
    """ψ_N where the (possibly non-monotonic) q-profile crosses ``target`` q, by linear
    interpolation across each sign change of q − target. Empty if never reached."""
    d = np.asarray(q, dtype=np.float64) - float(target)
    psi = np.asarray(psi_n, dtype=np.float64)
    out: list[float] = []
    sign_change = np.flatnonzero(np.diff(np.sign(d)) != 0)
    for i in sign_change:
        d0, d1 = d[i], d[i + 1]
        if d1 != d0:
            out.append(float(psi[i] - d0 * (psi[i + 1] - psi[i]) / (d1 - d0)))
    return out


def q_range(q_psi: NDArray[np.floating]) -> tuple[float, float]:
    """(q_min, q_max) over the profile, ignoring NaNs."""
    q = np.asarray(q_psi, dtype=np.float64)
    return float(np.nanmin(q)), float(np.nanmax(q))


def resonant_surfaces(
    q_psi: NDArray[np.floating],
    psi_n: NDArray[np.floating],
    n: int,
    *,
    m_max: int = 15,
) -> list[RationalSurface]:
    """All q = m/n rational surfaces present in the profile for toroidal number ``n``.

    Scans |m| = 1…``m_max``; a surface exists when q = m/|n| lies within [q_min, q_max].
    The ψ_N reported is the *outermost* crossing (largest ψ_N) — the mode's resonance is
    conventionally the outer one for the higher-order rationals. Returns them sorted by m.
    """
    na = abs(int(n))
    if na == 0:
        return []
    qmin, qmax = q_range(q_psi)
    out: list[RationalSurface] = []
    for m in range(1, m_max + 1):
        qt = m / na
        if qmin <= qt <= qmax:
            xs = _crossings(psi_n, q_psi, qt)
            psi_loc = max(xs) if xs else float("nan")
            out.append(RationalSurface(m=m, n=na, q=qt, psi_n=psi_loc))
    return out


def anchor_poloidal_m(
    m_values: NDArray[np.integer],
    mac_values: NDArray[np.floating],
    n: int,
    q_psi: NDArray[np.floating],
    psi_n: NDArray[np.floating],
    *,
    alias_margin: float = 0.1,
    m_max: int = 15,
) -> MAnchorResult:
    """Pick the physical poloidal m from the MAC spectrum using the q-profile.

    The raw MAC argmax is easily an alias on a sparse poloidal array. Among the MAC
    *alias set* — the candidates within ``alias_margin`` MAC of the best — keep only those
    whose |m|/|n| has a real q surface, and choose the highest-MAC survivor. If the raw
    winner is itself physical, nothing changes; if it is not (e.g. m/n below q_min) it is
    replaced and ``corrected`` is set. Sign of m follows the MAC (helicity), the q test
    uses |m|.
    """
    ms = np.asarray(m_values)
    macs = np.asarray(mac_values, dtype=np.float64)
    na = abs(int(n))
    qmin, qmax = q_range(q_psi)

    best_idx = int(np.argmax(macs))
    raw_m = int(ms[best_idx])

    def resonates(m_abs: int) -> bool:
        return na > 0 and 1 <= m_abs <= m_max and qmin <= m_abs / na <= qmax

    # alias set: candidates within the MAC margin of the best (excluding q=0/trivial)
    alias_mask = macs >= macs[best_idx] - alias_margin
    allowed_ms = sorted({abs(int(m)) for m in ms[alias_mask] if resonates(abs(int(m)))})

    chosen_idx = best_idx
    corrected = False
    if not resonates(abs(raw_m)):
        # raw winner is unphysical → take the best-MAC alias that does resonate
        candidates = [i for i in np.argsort(macs)[::-1] if resonates(abs(int(ms[i])))]
        if candidates:
            chosen_idx = int(candidates[0])
            corrected = True

    chosen_m = int(ms[chosen_idx])
    q_surface = abs(chosen_m) / na if resonates(abs(chosen_m)) else None
    psi_loc: float | None = None
    if q_surface is not None:
        xs = _crossings(psi_n, q_psi, q_surface)
        psi_loc = max(xs) if xs else None

    return MAnchorResult(
        chosen_m=chosen_m,
        q_surface=q_surface,
        psi_n=psi_loc,
        corrected=corrected,
        raw_m=raw_m,
        allowed_ms=allowed_ms,
        q_min=qmin,
        q_max=qmax,
    )
