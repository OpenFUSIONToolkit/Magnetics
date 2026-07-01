"""SLCONTOUR sensor geometry reads the shot-segmented device table.

Regression guard: the device JSON is shot-segmented (``sensors[c]["segments"]``),
but ``omfit_compat.sensor_geometry`` used to read the flat ``sensors[c]["r"]``,
which returns NaN under the segmented schema. All-NaN sensor extents make the QS
fit's basis matrix NaN and the SVD never converges. These tests need only the
committed device JSON — no fetched HDF5.
"""

from __future__ import annotations

import numpy as np

from magnetics._slcontour import omfit_compat as oc

# Integrated Bp LFS midplane channels the QS (SLCONTOUR) fit uses; present at a
# modern shot.
_QS_CHANNELS = ["MPID66M067", "MPID66M097", "MPID66M127"]
_MODERN_SHOT = 184928

_EXTENT_COORDS = [
    "r_end1",
    "r_end2",
    "z_end1",
    "z_end2",
    "phi_end1",
    "phi_end2",
    "theta_end1",
    "theta_end2",
]


def test_sensor_geometry_extents_are_finite():
    geo = oc.sensor_geometry("DIII-D", shot=_MODERN_SHOT)
    for ch in _QS_CHANNELS:
        sel = geo.sel(channel=ch)
        for coord in _EXTENT_COORDS:
            v = float(sel[coord].values)
            assert np.isfinite(v), f"{ch}.{coord} is not finite ({v})"


def test_sensor_geometry_matches_active_segment():
    # The resolved r/z/phi must equal the segment active at the shot (not NaN,
    # not a different era's value).
    from magnetics.data import devices

    dev = devices.load_device("diiid")
    geo = oc.sensor_geometry("DIII-D", shot=_MODERN_SHOT)
    for ch in _QS_CHANNELS:
        want = devices.geometry_at(dev, ch, _MODERN_SHOT)
        assert want is not None
        sel = geo.sel(channel=ch)
        for field in ("r", "z", "phi", "tilt", "length"):
            assert float(sel[field].values) == want[field]


def test_sensor_geometry_shot_none_falls_back_to_earliest():
    # Without a shot, resolution falls back to the earliest segment rather than NaN.
    geo = oc.sensor_geometry("DIII-D")
    sel = geo.sel(channel=_QS_CHANNELS[0])
    assert np.isfinite(float(sel["r_end1"].values))
