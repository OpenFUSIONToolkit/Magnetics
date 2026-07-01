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
