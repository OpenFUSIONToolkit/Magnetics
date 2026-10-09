"""Per-|n| rotating-mode amplitude (mode_shape.mode_amplitude_by_n) on a synthetic,
unevenly spaced toroidal array carrying two modes at different frequencies."""

import numpy as np

from magnetics.core.mode_shape import mode_amplitude_by_n
from magnetics.core.spectral import array_shape_spectrum

# Uneven DIII-D-like toroidal spacing: a strong n=1 projects partly onto n=2/3 here.
PHI = np.array([20, 67, 97, 127, 132, 137, 157, 200, 247, 277, 307, 312, 322, 340.0])


def _two_modes(a1=2.0, a2=1.0, noise=0.02, seed=0):
    rng = np.random.default_rng(seed)
    fs = 200_000
    t = np.linspace(0, 0.05, int(fs * 0.05), endpoint=False)
    sigs = np.vstack(
        [
            a1 * np.sin(2 * np.pi * 6000.0 * t - np.deg2rad(1 * p))
            + a2 * np.sin(2 * np.pi * 12000.0 * t - np.deg2rad(2 * p))
            + noise * rng.standard_normal(t.size)
            for p in PHI
        ]
    )
    return array_shape_spectrum(sigs, t), t


def test_one_trace_per_abs_n_with_the_right_amplitudes_and_frequencies():
    spec, _ = _two_modes()
    r = mode_amplitude_by_n(spec, PHI, n_slices=20)
    assert list(r.abs_n) == [0, 1, 2, 3, 4, 5]
    assert r.amplitude.shape == r.freq_khz.shape == (6, r.t_ms.size)
    a1, a2 = np.nanmedian(r.amplitude[1]), np.nanmedian(r.amplitude[2])
    assert np.isclose(a1 / a2, 2.0, rtol=0.1)  # 2:1 input ratio recovered
    assert np.allclose(r.freq_khz[1], 6.0, atol=1.0)
    assert np.allclose(r.freq_khz[2], 12.0, atol=1.0)


def test_strong_mode_does_not_echo_into_other_n():
    # n=1 alone: the n=2…5 traces may only carry noise-owned cells, far below n=1.
    spec, _ = _two_modes(a2=0.0)
    r = mode_amplitude_by_n(spec, PHI, n_slices=20)
    a1 = np.nanmedian(r.amplitude[1])
    for n in (2, 3, 4, 5):
        row = r.amplitude[n]
        assert np.all(np.isnan(row)) or np.nanmax(row) < 0.1 * a1
