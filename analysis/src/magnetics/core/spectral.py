"""Device-agnostic spectral math — a real STFT spectrogram + a single-frequency
phase extraction. Pure numpy (no scipy); operates on plain arrays.

This is the genuine rotating-mode primitive (MODESPEC-style): turn a Ḃ time series
into power vs (time, frequency). It is intentionally simple (Hann-windowed STFT,
log power) — the n-coloring / mode fitting layer comes later.
"""
from __future__ import annotations

import numpy as np


def spectrogram(data, dt_s: float, *, nperseg: int = 1024, overlap: float = 0.5,
                fmax_khz: float | None = 50.0, max_time_bins: int = 240):
    """Hann-windowed STFT. Returns (t_ms, f_khz, power_log) with power row-major
    [freq][time] to match the heatmap `z[y][x]` convention.
    """
    y = np.asarray(data, dtype=float)
    n = y.size
    nperseg = int(min(nperseg, max(16, n)))
    step = max(1, int(nperseg * (1.0 - overlap)))
    starts = np.arange(0, max(1, n - nperseg + 1), step)
    # cap the number of time columns so transport stays small/snappy
    if starts.size > max_time_bins:
        starts = starts[np.linspace(0, starts.size - 1, max_time_bins).astype(int)]

    win = np.hanning(nperseg)
    freqs = np.fft.rfftfreq(nperseg, d=dt_s)  # Hz
    keep = np.ones(freqs.size, dtype=bool)
    if fmax_khz is not None:
        keep = freqs <= fmax_khz * 1e3
        if keep.sum() < 2:
            keep = np.ones(freqs.size, dtype=bool)

    cols = []
    for s in starts:
        seg = y[s:s + nperseg]
        if seg.size < nperseg:
            seg = np.pad(seg, (0, nperseg - seg.size))
        spec = np.fft.rfft((seg - seg.mean()) * win)
        cols.append((np.abs(spec) ** 2)[keep])

    power = np.array(cols).T  # [freq][time]
    power_log = np.log10(power + 1e-30)
    t_ms = (starts + nperseg / 2.0) * dt_s * 1e3
    f_khz = freqs[keep] / 1e3
    return t_ms, f_khz, power_log


def phase_at_frequency(signals, dt_s: float, f0_hz: float) -> np.ndarray:
    """Phase (deg, 0..360) of each row of `signals` at frequency f0 via a
    single-bin DFT. `signals` is [n_channels, n_samples]. Used for phase-vs-φ
    mode-number fits.
    """
    sig = np.atleast_2d(np.asarray(signals, dtype=float))
    n = sig.shape[1]
    t = np.arange(n) * dt_s
    ref = np.exp(-2j * np.pi * f0_hz * t)
    proj = (sig - sig.mean(axis=1, keepdims=True)) @ ref
    return np.rad2deg(np.angle(proj)) % 360.0
