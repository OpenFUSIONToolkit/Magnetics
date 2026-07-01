"""Elongation straight-field-line θ* correction (core.geometry.elongation_theta_star).
Pure math — no fetched data, runs in CI."""

from __future__ import annotations

import math

import numpy as np

from magnetics.core import geometry


def test_elongation_theta_star_identity_and_known():
    # κ = 1 is the identity
    th = [0.0, 30.0, 45.0, 90.0, 135.0, 180.0, 270.0]
    assert np.allclose(geometry.elongation_theta_star(th, 1.0), th)
    # known elongated value: tan θ = κ tan θ*  →  θ*(45°, κ=1.8)
    got = geometry.elongation_theta_star([45.0], 1.8)[0]
    expect = (
        math.degrees(math.atan2(math.sin(math.radians(45)), 1.8 * math.cos(math.radians(45))))
        % 360.0
    )
    assert abs(got - expect) < 1e-9
    # the four midplane/crown crossings are fixed points for any κ
    assert np.allclose(
        geometry.elongation_theta_star([0, 90, 180, 270], 1.9), [0, 90, 180, 270], atol=1e-6
    )
