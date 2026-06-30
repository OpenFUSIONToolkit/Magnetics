"""GUI ⇄ analysis contract adapter for the ``spectrogram`` result.

Serializes the physics-core results from :mod:`magnetics.core.spectral` into the
plot-ready frame shapes defined in ``docs/CONTRACT.md`` (PR #4), and streams them
coarse → fine. Pure and JSON-able — dicts of Python lists/floats/ints, no numpy
scalars, no I/O, no transport. The service layer (owned by the Interfacers) wraps
:func:`stream_spectrogram` in the SSE endpoint.

Contract decisions encoded here (the answers to the doc's open questions):
  * ``power`` is **linear** (tagged ``scale="linear"``); the GUI applies any log.
  * ``n_map`` shares the **exact** ``(t_ms, f_kHz)`` grid as ``spectrogram``.
  * ``power``/``n`` arrays are oriented ``[i_f][i_t]`` (row = frequency, col = time)
    to match a Plotly heatmap ``z`` (y = freq, x = time).
  * ``phase_fit`` slice ``(t0, f)`` is param-driven; ``f`` defaults to the
    peak-power bin at ``t0``. Built to follow the GUI cursor (just re-call).
  * ``coherence`` (1-D vs frequency, at the ``t0`` slice) is included.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
from numpy.typing import NDArray

from magnetics.core.spectral import (
    SpectrogramResult,
    compute_spectrogram,
    extract_mode_at_frequency,
    fit_toroidal_mode,
    stft_layout,
)

CONTRACT_VERSION = "0.1"
_ROUND = 4       # decimal places for bounded axes/coherence/phase
_POWER_SIGFIG = 4  # significant figures for power (spans many decades; log-displayed)


# ---------------------------------------------------------------------------
# small helpers — everything returned is JSON-native (list/float/int/bool)
# ---------------------------------------------------------------------------


def _round_list(a: NDArray[np.floating]) -> list[float]:
    return np.round(np.asarray(a, dtype=np.float64), _ROUND).tolist()


def _sigfig(a: NDArray[np.floating], sig: int = _POWER_SIGFIG) -> NDArray[np.floating]:
    """Round to ``sig`` significant figures — shrinks JSON for wide-dynamic-range
    arrays (e.g. power ~1e5) far more than fixed decimals, at display-irrelevant cost."""
    # Drop non-finite first: JSON has no NaN/Infinity, and the GUI's JSON.parse rejects
    # the tokens Python's json would emit. Power is finite upstream; this is a backstop.
    a = np.nan_to_num(np.asarray(a, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    out = a.copy()
    nz = a != 0
    if np.any(nz):
        scale = 10.0 ** (np.floor(np.log10(np.abs(a[nz]))) - (sig - 1))
        out[nz] = np.round(a[nz] / scale) * scale
    return out


def _freq_mask(f_khz: NDArray[np.floating], fmin: float | None, fmax: float | None) -> NDArray[np.bool_]:
    mask = np.ones(f_khz.shape, dtype=bool)
    if fmin is not None:
        mask &= f_khz >= fmin
    if fmax is not None:
        mask &= f_khz <= fmax
    return mask


def _time_mask(t_ms: NDArray[np.floating], tmin: float | None, tmax: float | None) -> NDArray[np.bool_]:
    mask = np.ones(t_ms.shape, dtype=bool)
    if tmin is not None:
        mask &= t_ms >= tmin
    if tmax is not None:
        mask &= t_ms <= tmax
    return mask


def _peak_freq_khz(
    spec: SpectrogramResult,
    t0_ms: float | None,
    fmin_khz: float | None,
    fmax_khz: float | None,
) -> float:
    """Peak-power frequency (kHz) within [fmin, fmax] at the t0 column of ``spec``."""
    f_khz = np.asarray(spec.frequency, dtype=np.float64) / 1e3
    fmask = _freq_mask(f_khz, fmin_khz, fmax_khz)
    if not np.any(fmask):
        fmask = np.ones_like(fmask)
    t_ms = np.asarray(spec.time, dtype=np.float64) * 1e3
    t_idx = (
        int(np.argmin(np.abs(t_ms - t0_ms)))
        if t0_ms is not None else t_ms.size // 2
    )
    col = np.asarray(spec.power[t_idx])
    band_idx = np.flatnonzero(fmask)
    return float(f_khz[band_idx[int(np.argmax(col[fmask]))]])


def _natural_columns(time: NDArray[np.floating], n_samples: int, slice_duration: float) -> int:
    """Time-column count at the native 50%-overlap hop (shares compute_spectrogram's
    geometry via stft_layout so the two cannot drift)."""
    dt = float(np.median(np.diff(np.asarray(time, dtype=np.float64))))
    return stft_layout(n_samples, 1.0 / dt, slice_duration)[2]


def _stage_targets(stages: tuple[float, ...], ceiling: int) -> list[int]:
    """Coarse→fine column budgets: fractions of the achievable ceiling, with
    consecutive duplicates dropped and the final budget pinned to full resolution.
    Avoids recomputing identical grids when a stage's fraction clamps to the ceiling."""
    targets: list[int] = []
    for frac in stages:
        t = min(ceiling, max(1, int(round(ceiling * frac))))
        if not targets or t != targets[-1]:
            targets.append(t)
    if targets[-1] != ceiling:
        targets.append(ceiling)
    return targets


# ---------------------------------------------------------------------------
# data-shape builders (one contract `data` block from a SpectrogramResult)
# ---------------------------------------------------------------------------


def build_spectrogram_data(
    spec: SpectrogramResult,
    *,
    fmin_khz: float | None = None,
    fmax_khz: float | None = None,
    tmin_ms: float | None = None,
    tmax_ms: float | None = None,
    t0_ms: float | None = None,
    phase_fit: dict[str, Any] | None = None,
    include_n_map: bool = True,
    include_coherence: bool = True,
) -> dict[str, Any]:
    """Build the contract ``data`` block for one (possibly partial) spectrogram.

    Converts s→ms and Hz→kHz, crops to the requested frequency/time band, orients
    the 2-D arrays as ``[i_f][i_t]``, and attaches the optional ``n_map``,
    ``coherence`` (1-D at the ``t0`` slice), and ``phase_fit`` blocks.
    """
    t_ms = np.asarray(spec.time, dtype=np.float64) * 1e3
    f_khz = np.asarray(spec.frequency, dtype=np.float64) / 1e3

    fmask = _freq_mask(f_khz, fmin_khz, fmax_khz)
    tmask = _time_mask(t_ms, tmin_ms, tmax_ms)

    f_sel = f_khz[fmask]
    t_sel = t_ms[tmask]

    # spec.power is (n_time, n_freq); transpose to (n_freq, n_time) then crop.
    power_ft = spec.power[np.ix_(tmask, fmask)].T  # (n_freq, n_time)

    data: dict[str, Any] = {
        "spectrogram": {
            "t_ms": _round_list(t_sel),
            "f_kHz": _round_list(f_sel),
            "power": _sigfig(power_ft).tolist(),
            "scale": "linear",
            "units": "cross-power (T/s)^2",
        }
    }

    if include_n_map:
        n_ft = spec.mode_number[np.ix_(tmask, fmask)].T  # (n_freq, n_time)
        data["n_map"] = {
            "t_ms": data["spectrogram"]["t_ms"],
            "f_kHz": data["spectrogram"]["f_kHz"],
            "n": n_ft.astype(int).tolist(),
        }

    if include_coherence and t_sel.size:
        t_idx = int(np.argmin(np.abs(t_ms - (t0_ms if t0_ms is not None else t_sel[t_sel.size // 2]))))
        coh_slice = np.asarray(spec.coherence[t_idx])[fmask]
        data["coherence"] = {
            "f_kHz": data["spectrogram"]["f_kHz"],
            "coh": _round_list(coh_slice),
            "t_ms": round(float(t_ms[t_idx]), _ROUND),
        }

    if phase_fit is not None:
        data["phase_fit"] = phase_fit

    return data


def build_phase_fit(
    signals: NDArray[np.floating],
    toroidal_angles: NDArray[np.floating],
    time: NDArray[np.floating],
    *,
    t0_ms: float | None = None,
    f_khz: float | None = None,
    n_range: tuple[int, int] = (-6, 6),
    t_window_ms: float = 8.0,
) -> dict[str, Any]:
    """Build the contract ``phase_fit`` block from a toroidal probe array.

    Evaluates per-probe phase at ``(t0, f)`` (``f`` = peak-power bin when ``None``),
    fits a toroidal mode number, and returns measured points plus the fitted line
    sampled over ``phi ∈ [0, 360]``.
    """
    t_s = np.asarray(time, dtype=np.float64)
    t_range = None
    nperseg = None
    if t0_ms is not None:
        half = t_window_ms * 1e-3 / 2.0
        t_range = (t0_ms * 1e-3 - half, t0_ms * 1e-3 + half)
        # Keep several Welch segments inside the window so coherence/amplitude
        # weighting is meaningful (a single segment gives coherence ≡ 1).
        dt = float(np.median(np.diff(t_s)))
        n_window = int(round(t_window_ms * 1e-3 / dt))
        # ~4–7 Welch segments, but never longer than the window itself (else scipy
        # silently falls back and the averaging — the whole point — is lost).
        nperseg = int(min(n_window, max(16, n_window // 4)))

    mode = extract_mode_at_frequency(
        np.asarray(signals, dtype=np.float64),
        np.asarray(toroidal_angles, dtype=np.float64),
        t_s,
        # None = auto-peak; an explicit f_khz (including 0.0 = DC) is honored as given.
        frequency=(f_khz * 1e3) if f_khz is not None else None,
        t_range=t_range,
        nperseg=nperseg,
    )
    fit = fit_toroidal_mode(mode, n_range=n_range)

    # Fitted line phase(phi) = c - n*phi (deg), unwrapped so the slope (= -n) is
    # visible; the GUI wraps for display. Sampled at the [0, 360] endpoints.
    phi_line = np.array([0.0, 360.0])
    phase_line = fit.intercept_deg - fit.n * phi_line

    return {
        "phi_deg": _round_list(fit.toroidal_angle),
        "phase_deg": _round_list(fit.phase),
        "fit": {
            "phi_deg": phi_line.tolist(),
            "phase_deg": _round_list(phase_line),
        },
        "n": fit.n,
        "resultant": round(fit.resultant, _ROUND),
        "t_ms": round(float(t0_ms), _ROUND) if t0_ms is not None else None,
        "f_kHz": round(float(mode.frequency) / 1e3, _ROUND),
    }


# ---------------------------------------------------------------------------
# frame envelope + streaming
# ---------------------------------------------------------------------------


def make_frame(
    data: dict[str, Any],
    *,
    progress: float,
    final: bool,
    meta: dict[str, Any] | None = None,
    type: str = "spectrogram",
) -> dict[str, Any]:
    """Wrap a ``data`` block in the shared contract frame envelope."""
    return {
        "type": type,
        "version": CONTRACT_VERSION,
        "progress": round(float(progress), 4),
        "final": bool(final),
        "meta": meta or {},
        "data": data,
    }


def stream_spectrogram(
    time: NDArray[np.floating],
    sig1: NDArray[np.floating],
    sig2: NDArray[np.floating],
    delta_phi: float,
    *,
    fmin_khz: float | None = None,
    fmax_khz: float | None = None,
    tmin_ms: float | None = None,
    tmax_ms: float | None = None,
    window: str = "hann",
    slice_duration: float = 0.001,
    max_columns: int = 2000,
    stages: tuple[float, ...] = (0.15, 0.4, 1.0),
    t0_ms: float | None = None,
    f_khz: float | None = None,
    signals: NDArray[np.floating] | None = None,
    toroidal_angles: NDArray[np.floating] | None = None,
    n_range: tuple[int, int] = (-6, 6),
    meta: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield contract frames for one spectrogram request, coarse → fine.

    Each stage recomputes the spectrogram at a larger time-column budget (the
    frequency axis is held fixed, so frames refine in place); the last stage is
    ``final=True``. The ``phase_fit`` and 1-D ``coherence`` are evaluated at the
    ``t0`` slice on every frame so the GUI cursor can drive them.

    Inputs mirror ``compute_spectrogram`` plus the contract params (``fmin/fmax``
    kHz, ``tmin/tmax`` ms, ``t0``). ``signals``/``toroidal_angles`` supply the full
    toroidal array for ``phase_fit``; with neither, the fit falls back to the
    (sig1, sig2) pair at relative angles ``[0, -delta_phi]``.
    """
    if not stages:
        raise ValueError("stages must be non-empty")

    # phase-fit array: full array if given, else the streamed pair at relative angles.
    if signals is None:
        signals = np.vstack([sig1, sig2])
        toroidal_angles = np.array([0.0, -float(delta_phi)])
    elif toroidal_angles is None:
        raise ValueError("toroidal_angles is required when signals is given")

    # default t0: midpoint of the requested time window
    if t0_ms is None:
        t_ms_all = np.asarray(time, dtype=np.float64) * 1e3
        lo = tmin_ms if tmin_ms is not None else float(t_ms_all[0])
        hi = tmax_ms if tmax_ms is not None else float(t_ms_all[-1])
        t0_ms = 0.5 * (lo + hi)

    # Trim to [tmin, tmax] up front so the STFT cost scales with the displayed window,
    # not the full record — cropping after compute would waste the FFT on dropped bins.
    if tmin_ms is not None or tmax_ms is not None:
        cmask = _time_mask(np.asarray(time, dtype=np.float64) * 1e3, tmin_ms, tmax_ms)
        time = np.asarray(time)[cmask]
        sig1 = np.asarray(sig1)[cmask]
        sig2 = np.asarray(sig2)[cmask]
        signals = np.asarray(signals)[:, cmask]

    # Coarse→fine column budgets, clamped to what the record can actually deliver so
    # no two frames recompute the same grid and the last frame is true full resolution.
    ceiling = min(max_columns, _natural_columns(time, int(np.asarray(sig1).size), slice_duration))
    targets = _stage_targets(stages, ceiling)
    n_frames = len(targets)

    for i, cols in enumerate(targets):
        spec = compute_spectrogram(
            time, sig1, sig2, delta_phi,
            slice_duration=slice_duration,
            window=window,
            max_columns=cols,
        )
        # Tie the phase-fit frequency to the displayed band + actual power: when the
        # caller doesn't pin f, pick the peak-power bin within [fmin, fmax] at the t0
        # column of *this* spectrogram (keeps phase_fit consistent with what's drawn).
        f_pick = f_khz if f_khz is not None else _peak_freq_khz(
            spec, t0_ms, fmin_khz, fmax_khz
        )
        phase_fit = build_phase_fit(
            signals, toroidal_angles, time,
            t0_ms=t0_ms, f_khz=f_pick, n_range=n_range,
        )
        data = build_spectrogram_data(
            spec,
            fmin_khz=fmin_khz, fmax_khz=fmax_khz,
            tmin_ms=tmin_ms, tmax_ms=tmax_ms,
            t0_ms=t0_ms, phase_fit=phase_fit,
        )
        yield make_frame(
            data,
            progress=(i + 1) / n_frames,
            final=(i == n_frames - 1),
            meta=meta,
        )


def spectrogram_oneshot(
    time: NDArray[np.floating],
    sig1: NDArray[np.floating],
    sig2: NDArray[np.floating],
    delta_phi: float,
    **kwargs: Any,
) -> dict[str, Any]:
    """The single ``final=True`` frame (one-shot endpoint / tests / mock)."""
    frame = None
    for frame in stream_spectrogram(
        time, sig1, sig2, delta_phi, stages=(1.0,), **kwargs
    ):
        pass
    assert frame is not None
    return frame
