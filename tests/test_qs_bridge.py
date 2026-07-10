"""qs_bridge adapters: the production QS output path (fit Dataset → kind-nodes).

Every adapter hard-codes the fit Dataset's variable names (`fit_coeffs`,
`fit_ns`, `red_chi_sq`, ...). If the upstream fit renames one, the node breaks —
the same silent schema-coupling failure class as the segmented-geometry bug. These
tests exercise every adapter on a real (synthetic-shot) fit and assert a dropped
variable *raises* rather than mis-serving.
"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from magnetics.core import qs_bridge
from magnetics.service import nodes


@pytest.fixture()
def fit_ds(synthetic_shot):
    return nodes._prep_qs_ds(synthetic_shot, {}).fit


_ADAPTERS = {
    "fit_to_qs_fit_node": "contour",
    "fit_to_phi_t_node": "contour",
    "fit_to_amplitude_node": "line",
    "fit_to_phase_t_node": "line",
    "fit_to_chi_sq_node": "line",
    "fit_to_fit_signals_node": "line",
    "fit_to_fit_residuals_node": "line",
    "fit_to_fit_quality_node": "metrics",
    "fit_to_svd_energy_node": "line",
    "fit_to_svd_condition_node": "line",
}


@pytest.mark.parametrize("fn_name,expected_kind", sorted(_ADAPTERS.items()))
def test_adapter_returns_expected_kind(fit_ds, fn_name, expected_kind):
    node = getattr(qs_bridge, fn_name)(fit_ds)
    assert node["kind"] == expected_kind


def test_dropping_a_required_variable_raises_not_silently_misserves(fit_ds):
    broken = fit_ds.drop_vars("fit_coeffs")
    with pytest.raises((KeyError, AttributeError)):
        qs_bridge.fit_to_qs_fit_node(broken)


def test_fit_quality_statuses_use_contract_vocabulary(fit_ds):
    node = qs_bridge.fit_to_fit_quality_node(fit_ds)
    statuses = [field["status"] for field in node["fields"] if "status" in field]

    assert statuses
    assert set(statuses) <= {"good", "warn", "bad"}


def test_amplitude_sigma_is_finite(fit_ds):
    node = qs_bridge.fit_to_amplitude_node(fit_ds)
    sigma = np.asarray(node["meta"]["sigma"], dtype=float)
    assert np.all(np.isfinite(sigma))


def test_svd_energy_node_is_monotonic_and_bounded(fit_ds):
    node = qs_bridge.fit_to_svd_energy_node(fit_ds)
    energy = np.asarray(node["series"][0]["y"], dtype=float)
    assert np.all(np.isfinite(energy))
    assert np.all(np.diff(energy) >= -1e-9)  # cumulative energy fraction is non-decreasing
    assert energy[-1] == pytest.approx(1.0, abs=1e-6)
    assert "rank" in node["meta"] and "reference_line" in node["meta"]


def test_svd_condition_node_is_finite_and_positive(fit_ds):
    node = qs_bridge.fit_to_svd_condition_node(fit_ds)
    cond = np.asarray(node["series"][0]["y"], dtype=float)
    assert np.all(np.isfinite(cond))
    assert np.all(cond >= 1.0)  # condition number is a ratio against the largest singular value
    assert node["meta"]["reference_line"] == fit_ds.attrs.get("fit_condition", 10.0)


def test_sigma_override_changes_amplitude_uncertainty(synthetic_shot):
    default_fit = nodes._prep_qs_ds(synthetic_shot, {}).fit
    overridden_fit = nodes._prep_qs_ds(synthetic_shot, {"sigma": "1.0"}).fit
    default_sigma = qs_bridge.fit_to_amplitude_node(default_fit)["meta"]["sigma"]
    overridden_sigma = qs_bridge.fit_to_amplitude_node(overridden_fit)["meta"]["sigma"]
    assert np.mean(overridden_sigma) > np.mean(default_sigma)


def test_fit_basis_param_reaches_fit(synthetic_shot):
    run = nodes._prep_qs_ds(synthetic_shot, {"fit_basis": "gaussian-point"})
    assert run.fit.attrs["fit_basis"] == "gaussian-point"


def test_fit_cond_param_reaches_fit(synthetic_shot):
    run = nodes._prep_qs_ds(synthetic_shot, {"fit_cond": "3.0"})
    assert run.fit.attrs["fit_condition"] == 3.0


def _single_mode_fit(n, m, phase_deg):
    """A minimal fit Dataset: one mode, complex coeff = exp(i·phase_deg), constant in time."""
    b = np.exp(1j * np.deg2rad(phase_deg))
    t_s = np.linspace(0.0, 0.01, 5)
    coeffs = np.full((1, t_s.size), b, dtype=complex)
    return xr.Dataset(
        {
            "fit_ns": ("mode", [n]),
            "fit_ms": ("mode", [m]),
            "fit_coeffs": (("mode", "time"), coeffs),
        },
        coords={"mode": [0], "time": t_s},
    )


def test_reconstruction_uses_minus_i_sign_convention():
    """A locked n=1, m=0 mode with spatial phase δ reconstructs as cos(φ − δ), so its
    δBp peak sits at φ = +δ. The buggy exp(+i…) reconstruction would mirror it to −δ
    (i.e. 360−δ). This is the discriminating case the old zero-phase test missed —
    it pins the convention shared by qs_bridge / qs_plots / OMFIT plot_magnetics_slice.
    """
    delta = 60.0
    ds = _single_mode_fit(n=1, m=0, phase_deg=delta)
    phi = np.linspace(0, 360, 361)
    theta = np.array([0.0])

    z = qs_bridge._reconstruct_grid(ds, phi, theta, t_idx=0)  # [n_theta, n_phi]
    peak_phi = float(phi[np.argmax(z[0])])

    assert abs(peak_phi - delta) < 2.0, (
        f"reconstructed peak at φ={peak_phi}°, expected ~{delta}° (−i convention); "
        f"a peak near {360 - delta}° means the exp(+i…) sign bug is back"
    )


def test_sigma_override_does_not_corrupt_fit_signal(synthetic_shot):
    """Regression: fit_signal was de-normalized by the dataset signal_sigma while the
    design matrix and RHS were normalized by the override sigma, scaling fit_signal
    by signal_sigma/override and corrupting residual and chi_sq (the coefficients
    stayed correct). With a uniform sigma the weighted LS solution is
    override-invariant: fit_signal must be identical, and chi_sq must scale by
    exactly (sigma_default / sigma_override)**2."""
    default = nodes._prep_qs_ds(synthetic_shot, {}).fit
    override = 1e-4
    overridden = nodes._prep_qs_ds(synthetic_shot, {"sigma": str(override)}).fit

    np.testing.assert_allclose(
        overridden["fit_coeffs"].values, default["fit_coeffs"].values, rtol=1e-9
    )
    np.testing.assert_allclose(
        overridden["fit_signal"].values, default["fit_signal"].values, rtol=1e-9
    )
    sig0 = float(np.nanmean(default["signal_sigma"].values))
    np.testing.assert_allclose(
        overridden["chi_sq"].values,
        default["chi_sq"].values * (sig0 / override) ** 2,
        rtol=1e-6,
    )


def test_default_fit_cond_is_inversion_cutoff_not_trust_threshold(synthetic_shot):
    """The default cutoff must be OMFIT SLCONTOUR's 1e3 inversion cutoff (1/rcond)
    at every layer. When it was 10 (the GUI's K-trust threshold), any fit with K in
    (10, 1e3) silently zeroed basis directions the reference fit keeps — and K(eff)
    read <= 10 by construction, so the quality panel looked healthiest exactly when
    the regularization was distorting the fit."""
    import inspect

    from magnetics.core import qs_fit

    # core default (what a direct fit() call regularizes with)
    assert inspect.signature(qs_fit.fit).parameters["fit_cond"].default == 1e3
    # service default (what a GUI request without fit_cond regularizes with)
    run = nodes._prep_qs_ds(synthetic_shot, {})
    assert run.fit.attrs["fit_condition"] == 1e3
