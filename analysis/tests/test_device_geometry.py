"""Device-description geometry: the JSON loader, the JSON-backed diiid mapping, and
the elongation θ* correction. These are pure (no fetched HDF5 needed) — they read the
committed data/device/diiid.json and core math, so they run in CI without data.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from magnetics.core import geometry
from magnetics.data import device_config, diiid


def test_load_diiid_config():
    dev = device_config.load("diiid")
    assert dev.name == "DIII-D"
    assert dev.R0 > 1.0
    assert dev.wall() is not None        # committed vessel wall
    # a known integrated-Bp probe carries real geometry + calibration fields
    s = dev.sensor("MPID1A011")
    assert s is not None and s.phi is not None and s.na is not None
    assert s.pair == "MPID1A199"


def test_unknown_device_raises():
    with pytest.raises(FileNotFoundError):
        device_config.load("not_a_device")


def test_phi_is_real_not_name_parsed():
    # the 3D I-coils are a few degrees off their name digits; the device file is exact
    assert abs(diiid.phi_of("IU30") - 32.7) < 0.5      # name says 30, truth is 32.7
    # a non-geometry equilibrium scalar has no toroidal angle
    assert diiid.phi_of("ip") is None


def test_theta_is_geometric_not_cosmetic():
    # MPID67A probes sit ~52° off the midplane (real), not a flat per-array offset
    assert abs(diiid.theta_of("MPID67A217") - 52.5) < 2.0
    assert diiid.has_geometry("MPID67A217")
    assert not diiid.has_geometry("ip")
    # theta = atan2(z, r-R0) reconstructed from the raw record
    dev = device_config.load("diiid")
    s = dev.sensor("MPID5A199")
    expect = math.degrees(math.atan2(s.z, s.r - dev.R0)) % 360.0
    assert abs(diiid.theta_of("MPID5A199") - expect) < 1e-6


def test_elongation_theta_star_identity_and_known():
    # κ = 1 is the identity
    th = [0.0, 30.0, 45.0, 90.0, 135.0, 180.0, 270.0]
    assert np.allclose(geometry.elongation_theta_star(th, 1.0), th)
    # known elongated value: tan θ = κ tan θ*  →  θ*(45°, κ=1.8)
    got = geometry.elongation_theta_star([45.0], 1.8)[0]
    expect = math.degrees(math.atan2(math.sin(math.radians(45)),
                                     1.8 * math.cos(math.radians(45)))) % 360.0
    assert abs(got - expect) < 1e-9
    # the four midplane/crown crossings are fixed points for any κ
    assert np.allclose(geometry.elongation_theta_star([0, 90, 180, 270], 1.9),
                       [0, 90, 180, 270], atol=1e-6)
