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


def test_fit_quality_statuses_use_the_contract_vocabulary(fit_ds):
    """The traffic-light status must be one of the GUI's Quality values
    (good/warn/bad = contracts.quality_for_k), not the old 'ok'/'error' strings
    which NodeView's QCOLOR can't color."""
    node = qs_bridge.fit_to_fit_quality_node(fit_ds)
    statuses = [f["status"] for f in node["fields"] if "status" in f]
    assert statuses  # the K (raw)/K (eff) rows carry a status
    assert all(s in {"good", "warn", "bad"} for s in statuses)


def test_amplitude_sigma_is_finite(fit_ds):
    node = qs_bridge.fit_to_amplitude_node(fit_ds)
    sigma = np.asarray(node["meta"]["sigma"], dtype=float)
    assert np.all(np.isfinite(sigma))
