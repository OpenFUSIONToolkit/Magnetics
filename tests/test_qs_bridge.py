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
}


@pytest.mark.parametrize("fn_name,expected_kind", sorted(_ADAPTERS.items()))
def test_adapter_returns_expected_kind(fit_ds, fn_name, expected_kind):
    node = getattr(qs_bridge, fn_name)(fit_ds)
    assert node["kind"] == expected_kind


def test_dropping_a_required_variable_raises_not_silently_misserves(fit_ds):
    broken = fit_ds.drop_vars("fit_coeffs")
    with pytest.raises((KeyError, AttributeError)):
        qs_bridge.fit_to_qs_fit_node(broken)


def test_amplitude_sigma_is_finite(fit_ds):
    node = qs_bridge.fit_to_amplitude_node(fit_ds)
    sigma = np.asarray(node["meta"]["sigma"], dtype=float)
    assert np.all(np.isfinite(sigma))


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
