"""Equivalence + peak-RAM tests for the block-batched ``_stft``.

The chunked engine is a pure memory refactor: it must return the *same* STFT as a
single batched transform while never materializing the full frame matrix. These
tests pin that with an independent per-frame reference (no call into ``_stft``), so
the equivalence is real and not a tautology, and demonstrate the peak-RAM drop on a
long signal with the shared ``measure()`` harness.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.fft import rfft
from scipy.signal import get_window

import magnetics.core.spectral as spectral
from magnetics.core.spectral import _stft, compute_spectrogram

from .bench_dataflow import format_measurement, measure


# ---------------------------------------------------------------------------
# Independent reference: the obvious per-frame definition _stft must reproduce.
# ---------------------------------------------------------------------------


def _reference_stft(
    signal: np.ndarray,
    n_fft: int,
    hop: int,
    window: np.ndarray,
    *,
    detrend: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame STFT written from scratch: loop the frames, detrend each, apply the
    window, rfft. Mirrors ``_stft``'s short-signal zero-pad branch but shares no code
    with it, so an agreement is evidence rather than circular."""
    n = signal.size
    if n < n_fft:
        frame = np.zeros(n_fft, dtype=signal.dtype)
        frame[:n] = signal
        if detrend:
            frame[:n] -= frame[:n].mean()
        return rfft(frame * window)[None, :], np.array([0], dtype=np.intp)

    starts = np.arange(0, n - n_fft + 1, hop, dtype=np.intp)
    rows = []
    for s in starts:
        frame = signal[s : s + n_fft].astype(signal.dtype, copy=True)
        if detrend:
            frame = frame - frame.mean()
        rows.append(rfft(frame * window))
    return np.stack(rows), starts


def _signal(n: int, *, dtype=np.float32, seed: int = 0) -> np.ndarray:
    """A deterministic signal with a slow linear trend, so detrend True/False differ."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    raw = (
        np.sin(2 * np.pi * t / 17.0)
        + 0.3 * np.cos(2 * np.pi * t / 5.0)
        + 0.5 * np.sin(2 * np.pi * t / 1024.0)  # slow drift the per-frame detrend removes
        + 0.05 * rng.standard_normal(n)
    )
    return raw.astype(dtype)


def _window(n_fft: int, *, dtype=np.float32) -> np.ndarray:
    return get_window("hann", n_fft, fftbins=True).astype(dtype)


# ---------------------------------------------------------------------------
# Equivalence across the geometry that decides the framing branches.
# ---------------------------------------------------------------------------

N_FFT = 64

# (label, signal_len, hop, detrend) — covers the short/zero-pad branch, the exactly-
# n_fft and n_fft+1 boundaries, 50%-overlap and an irregular hop, both detrend modes,
# and a many-frame case that crosses several _STFT_CHUNK block boundaries.
_CASES = [
    ("short_detrend", N_FFT - 24, 8, True),
    ("short_no_detrend", N_FFT - 24, 8, False),
    ("exactly_n_fft", N_FFT, N_FFT // 2, True),
    ("n_fft_plus_1_hop1", N_FFT + 1, 1, True),
    ("n_fft_plus_1_half_hop", N_FFT + 1, N_FFT // 2, False),
    ("many_half_hop", 5000, N_FFT // 2, True),
    ("many_irregular_hop", 5000, 37, False),
    ("many_unit_hop_multi_block", 4000, 1, True),
]


@pytest.mark.parametrize("label, n, hop, detrend", _CASES, ids=[c[0] for c in _CASES])
def test_matches_independent_reference(label, n, hop, detrend):
    sig = _signal(n)
    win = _window(N_FFT)

    spec, starts = _stft(sig, N_FFT, hop, win, detrend=detrend)
    ref_spec, ref_starts = _reference_stft(sig, N_FFT, hop, win, detrend=detrend)

    np.testing.assert_array_equal(starts, ref_starts)
    assert spec.dtype == ref_spec.dtype == np.complex64
    assert spec.shape == (starts.size, N_FFT // 2 + 1)
    # Tight for complex64: any framing/window/detrend error is O(signal); the residual
    # is pocketfft's 1-D vs batched float32 rounding, scaled to the spectrum peak the
    # way FFTs are compared across implementations.
    np.testing.assert_allclose(spec, ref_spec, rtol=1e-4, atol=1e-4 * float(np.abs(ref_spec).max()))


def test_many_frames_actually_cross_chunk_boundary():
    """Guard the test's own premise: the multi-block case must exceed one block."""
    sig = _signal(4000)
    _, starts = _stft(sig, N_FFT, 1, _window(N_FFT))
    assert starts.size > spectral._STFT_CHUNK


def test_float64_path_promotes_to_complex128():
    """The preallocated output dtype tracks the working precision: a float64 signal
    and window must yield complex128, matching a single batched rfft."""
    sig = _signal(2000, dtype=np.float64)
    win = _window(N_FFT, dtype=np.float64)

    spec, starts = _stft(sig, N_FFT, N_FFT // 2, win)
    ref_spec, ref_starts = _reference_stft(sig, N_FFT, N_FFT // 2, win)

    np.testing.assert_array_equal(starts, ref_starts)
    assert spec.dtype == ref_spec.dtype == np.complex128
    np.testing.assert_allclose(spec, ref_spec, rtol=1e-12, atol=1e-12 * float(np.abs(ref_spec).max()))


# ---------------------------------------------------------------------------
# compute_spectrogram still recovers the synthetic mode with unchanged shapes.
# ---------------------------------------------------------------------------


def test_compute_spectrogram_recovers_mode_and_shapes(synthetic_n2):
    d = synthetic_n2
    result = compute_spectrogram(
        d["time"], d["sig1"], d["sig2"], d["delta_phi"], slice_duration=0.01
    )

    n_times, n_freqs = len(result.time), len(result.frequency)
    n_modes = len(result.mode_indices)
    assert result.power.shape == (n_times, n_freqs)
    assert result.coherence.shape == (n_times, n_freqs)
    assert result.mode_number.shape == (n_times, n_freqs)
    assert result.rms_by_mode.shape == (n_times, n_modes)

    for i in range(n_times):
        peak = np.argmax(result.power[i])
        assert abs(result.mode_number[i, peak]) == d["n_true"]


# ---------------------------------------------------------------------------
# Peak-RAM: chunked vs. the old single-batch allocation on a long signal.
# ---------------------------------------------------------------------------


def test_chunked_stft_lowers_peak_ram(monkeypatch, capsys):
    # ~4000 frames at n_fft=512: the single-batch frame matrix is the large
    # transient the block loop removes; the returned spectrum is identical to both.
    n_fft, hop = 512, 128
    sig = _signal(512_000)
    win = _window(n_fft)
    default_chunk = spectral._STFT_CHUNK

    # sink=... silences the harness's own print; the measurement still lands in the
    # holder, and we print one clean pair below under capsys.disabled().

    # Before: one block spanning every frame reproduces the pre-refactor allocation.
    monkeypatch.setattr(spectral, "_STFT_CHUNK", 1 << 30)
    with measure("_stft single-batch (before)", sink=lambda _m: None) as before:
        spec_full, _ = _stft(sig, n_fft, hop, win)

    monkeypatch.setattr(spectral, "_STFT_CHUNK", default_chunk)
    with measure(f"_stft chunked={default_chunk} (after)", sink=lambda _m: None) as after:
        spec_chunked, _ = _stft(sig, n_fft, hop, win)

    # Same bytes out, strictly smaller Python-heap high-water mark in.
    np.testing.assert_array_equal(spec_full, spec_chunked)
    assert after[0].py_peak_bytes < before[0].py_peak_bytes

    with capsys.disabled():
        print()
        print(format_measurement(before[0]))
        print(format_measurement(after[0]))
