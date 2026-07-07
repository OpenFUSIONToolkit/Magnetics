"""Pairwise-difference treatment in the QS fit (`qs_fit` + `qs_device`).

A differential magnetic sensor (`pair != "None"` — the MPID/ISLD/ESLD families) reports
`field(X) − field(pair)`, so its design-matrix column must be `(basis(X) − basis(pair)) / 2`
(ported from OMFIT `fit_magnetics.py:340`). These tests pin that treatment: the unit test
checks the assembled design matrix column-by-column for a mixed paired/unpaired array, and
the pipeline test confirms detection flows end-to-end on the synthetic shot.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

from magnetics.core import qs_fit
from magnetics.service import nodes


def _min_prepared():
    """A minimal PREPARED-style Dataset: channel s0 is paired (pair ends set), s1 is
    unpaired (pair ends NaN). Cylindrical geometry, constant σ."""
    t = np.linspace(0.0, 0.01, 8)
    ds = xr.Dataset(
        {
            "signal": (("channel", "time"), np.ones((2, t.size))),
            "signal_sigma": ("channel", np.full(2, 2.0e-5)),
            "phi_end1": ("channel", np.array([10.0, 20.0])),
            "phi_end2": ("channel", np.array([12.0, 22.0])),
            "theta_end1": ("channel", np.array([0.0, 0.0])),
            "theta_end2": ("channel", np.array([0.0, 0.0])),
            # s0 paired to a sensor near φ=100°; s1 unpaired → NaN
            "pair_phi_end1": ("channel", np.array([100.0, np.nan])),
            "pair_phi_end2": ("channel", np.array([102.0, np.nan])),
            "pair_theta_end1": ("channel", np.array([0.0, np.nan])),
            "pair_theta_end2": ("channel", np.array([0.0, np.nan])),
        },
        coords={"channel": ["s0", "s1"], "time": t},
    )
    ds.attrs.update(helicity=-1, device="DIII-D", sigma_type=2.0e-5)
    return ds


def test_paired_column_is_differenced_unpaired_is_not():
    ds = _min_prepared()
    fitds = qs_fit.fit(ds, ns=(1,), ms=(0,), fit_basis="sinusoidal-point", verbose=False)

    assert int(fitds.attrs["n_paired"]) == 1  # only s0 is paired

    # Rebuild the expected differenced design column from the public primitive.
    fbf = qs_fit.form_basis_function
    sigma = ds["signal_sigma"].values
    x1, x2 = ds["phi_end1"].values, ds["phi_end2"].values
    y1, y2 = ds["theta_end1"].values, ds["theta_end2"].values
    px1, px2 = ds["pair_phi_end1"].values, ds["pair_phi_end2"].values
    py1, py2 = ds["pair_theta_end1"].values, ds["pair_theta_end2"].values
    has_pair = np.isfinite(px1)

    fmn = fbf(1, 0, x1, x2, y1, y2, "sinusoidal-point") / sigma
    fmn_pair = fbf(1, 0, px1, px2, py1, py2, "sinusoidal-point") / sigma
    expected = np.where(has_pair, (fmn - fmn_pair) / 2.0, fmn)  # [2] complex

    # n=1,m=0 point basis is complex → the design matrix carries a (real, imag) column
    # pair; reconstruct the complex column and compare per channel.
    basis = fitds["basis"].values  # (n_channels, n_cols)
    assert basis.shape == (2, 2)
    complex_col = basis[:, 0] + 1j * basis[:, 1]
    np.testing.assert_allclose(complex_col, expected, rtol=1e-6, atol=1e-9)

    # Sanity: the paired channel's column actually differs from the plain single-sensor
    # basis (i.e. the differencing is not a no-op), while the unpaired one matches it.
    plain = fmn
    assert not np.isclose(complex_col[0], plain[0])
    assert np.isclose(complex_col[1], plain[1])


def test_pipeline_reports_all_midplane_channels_paired(synthetic_shot):
    """The default Bp_LFS_midplane fit is the 10 MPID66M* probes — all paired."""
    run = nodes._prep_qs_ds(synthetic_shot, {})
    assert run.fit.attrs["n_paired"] == 10
    assert run.fit.sizes["channel"] == 10
