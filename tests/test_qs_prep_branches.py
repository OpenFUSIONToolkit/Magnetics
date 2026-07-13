"""qs_prep branches that the end-to-end pipeline tests never reach.

The GUI offers four detrend types, but only `baseline` ever ran under test; the
`linear`/`endpoints` estimators and the DIII-D 2019 ESLD wiring-swap branch were
complete dead zones. All offline: `_detrend` is exercised directly on hand-built
Datasets, the swap through `prepare()` on a minimal ShotData.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from magnetics.core.qs_io_data import ShotData
from magnetics.core.qs_prep import _detrend, prepare

TIME = np.linspace(0.0, 1.0, 201)  # s


def _ds(*signals):
    names = [f"c{i}" for i in range(len(signals))]
    return xr.Dataset(
        {"signal": (("channel", "time"), np.array(signals, dtype=float))},
        coords={"channel": names, "time": TIME},
    )


def _quiet(*a):
    pass


class TestDetrend:
    def test_none_is_a_no_op(self):
        ds = _ds(np.sin(2 * np.pi * 5 * TIME) + 3.0)
        before = ds["signal"].values.copy()
        _detrend(ds, ds["channel"].values, "none", (0.0, 0.2), _quiet)
        np.testing.assert_array_equal(ds["signal"].values, before)

    def test_baseline_removes_in_band_mean(self):
        ds = _ds(np.sin(2 * np.pi * 50 * TIME) + 7.5)
        _detrend(ds, ds["channel"].values, "baseline", (0.0, 0.2), _quiet)
        band = (TIME >= 0.0) & (TIME <= 0.2)
        assert np.mean(ds["signal"].values[0, band]) == pytest.approx(0.0, abs=1e-12)

    def test_linear_removes_a_pure_ramp_everywhere(self):
        # The trend is fit inside the band but subtracted over the WHOLE record —
        # a pure ramp must vanish everywhere, not just in the band.
        ds = _ds(4.0 * TIME + 2.0)
        _detrend(ds, ds["channel"].values, "linear", (0.1, 0.4), _quiet)
        np.testing.assert_allclose(ds["signal"].values[0], 0.0, atol=1e-10)

    def test_linear_preserves_oscillation_on_top_of_ramp(self):
        osc = np.sin(2 * np.pi * 40 * TIME)
        ds = _ds(osc + 4.0 * TIME + 2.0)
        _detrend(ds, ds["channel"].values, "linear", (0.0, 1.0), _quiet)
        # residual is the oscillation (the LSQ line through a whole number of
        # periods absorbs none of it to good approximation)
        assert np.corrcoef(ds["signal"].values[0], osc)[0, 1] > 0.999

    def test_endpoints_zeroes_the_band_endpoints(self):
        rng = np.random.default_rng(7)
        ds = _ds(rng.standard_normal(TIME.size) + 3.0 * TIME)
        band = (0.1, 0.9)
        sel = (TIME >= band[0]) & (TIME <= band[1])
        first, last = np.flatnonzero(sel)[[0, -1]]
        _detrend(ds, ds["channel"].values, "endpoints", band, _quiet)
        # the line through the two band endpoints is removed → both go to ~0
        assert ds["signal"].values[0, first] == pytest.approx(0.0, abs=1e-10)
        assert ds["signal"].values[0, last] == pytest.approx(0.0, abs=1e-10)

    def test_per_channel_independence(self):
        ds = _ds(np.full(TIME.size, 5.0), np.full(TIME.size, -2.0))
        _detrend(ds, ds["channel"].values, "baseline", (0.0, 1.0), _quiet)
        np.testing.assert_allclose(ds["signal"].values, 0.0, atol=1e-12)

    def test_unknown_type_raises(self):
        ds = _ds(TIME)
        with pytest.raises(ValueError, match="detrend_type"):
            _detrend(ds, ds["channel"].values, "quadratic", (0.0, 1.0), _quiet)


# ---------------------------------------------------------------------------
# DIII-D 2019 wiring mix-up: ESLD66M079 ⇄ ESLD66M319 swap for shot > 177705
# ---------------------------------------------------------------------------


def _shotdata(shot, ch_a="ESLD66M079", ch_b="ESLD66M319"):
    t = np.linspace(2.85, 3.05, 2001)  # spans prepare()'s default (2.9, 3.0) trim
    raw = xr.Dataset(
        {
            "signal": (
                ("channel", "time"),
                np.vstack([np.full(t.size, 1.0), np.full(t.size, 2.0)]),
            ),
            "signal_sigma": (("channel",), np.array([2e-5, 2e-5])),
        },
        coords={"channel": [ch_a, ch_b], "time": t},
    )
    plasma = xr.Dataset(coords={"time": t})
    return ShotData(shot=shot, device="DIII-D", raw=raw, plasma=plasma)


def test_esld_2019_swap_applies_after_the_wiring_fix_shot():
    sd = _shotdata(180000)  # > 177705
    prepared, _ = prepare(sd, channel_filter=".*", detrend_type="none", verbose=False)
    # channel labeled 079 must carry 319's samples and vice versa
    assert float(prepared["signal"].sel(channel="ESLD66M079").values[0]) == pytest.approx(2.0)
    assert float(prepared["signal"].sel(channel="ESLD66M319").values[0]) == pytest.approx(1.0)


def test_esld_swap_skipped_for_pre_fix_shots_and_partial_pairs():
    sd = _shotdata(170000)  # < 177705: wiring was correct, no swap
    prepared, _ = prepare(sd, channel_filter=".*", detrend_type="none", verbose=False)
    assert float(prepared["signal"].sel(channel="ESLD66M079").values[0]) == pytest.approx(1.0)

    # only one of the pair present → swap must not run (guard on both names)
    sd = _shotdata(180000, ch_b="MPID66M067")
    prepared, _ = prepare(sd, channel_filter=".*", detrend_type="none", verbose=False)
    assert float(prepared["signal"].sel(channel="ESLD66M079").values[0]) == pytest.approx(1.0)
