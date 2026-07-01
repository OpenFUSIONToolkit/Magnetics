"""Core geometry design metrics: the condition number K (SLCONTOUR's array-quality
metric driving the GUI traffic light) and the Fourier design matrix it's built on."""

from __future__ import annotations

import math

import numpy as np

from magnetics.core import geometry


def test_condition_number_small_for_well_spread_array():
    phi = np.linspace(0, 360, 8, endpoint=False)  # 8 evenly-spaced probes
    k = geometry.condition_number(phi, n_max=3)
    assert math.isfinite(k) and 1.0 <= k < 3.0


def test_condition_number_large_but_finite_for_clustered_array():
    phi = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0])  # tightly clustered
    k = geometry.condition_number(phi, n_max=3)
    assert math.isfinite(k) and k > 10.0  # poorly resolved, but not degenerate


def test_condition_number_inf_when_too_few_probes():
    # n_max=3 needs 1+2*3 = 7 columns; 4 probes can't constrain it.
    assert geometry.condition_number([0.0, 90.0, 180.0, 270.0], n_max=3) == float("inf")


def test_condition_number_unusable_for_degenerate_all_equal():
    # All probes at one angle → rank-deficient design matrix. Float SVD yields a
    # tiny (not exactly zero) smallest singular value, so K is enormous but finite —
    # either way it lands well past the "bad" threshold (>20).
    k = geometry.condition_number([45.0] * 8, n_max=3)
    assert k > 1e6


def test_fourier_design_matrix_structure():
    phi = np.array([0.0, 30.0, 90.0])
    a = geometry.fourier_design_matrix(phi, n_max=2)
    assert a.shape == (3, 1 + 2 * 2)  # [1, cos φ, sin φ, cos 2φ, sin 2φ]
    np.testing.assert_allclose(a[:, 0], 1.0)  # constant column
    r = np.deg2rad(phi)
    np.testing.assert_allclose(a[:, 1], np.cos(r))
    np.testing.assert_allclose(a[:, 2], np.sin(r))
    np.testing.assert_allclose(a[:, 3], np.cos(2 * r))
