"""Quasi-stationary pipeline end-to-end, against the synthetic shot.

Spans qs_io_data → qs_device.sensor_geometry → qs_prep → qs_fit → qs_bridge → contracts
— the full SLCONTOUR path. This is the coverage that was missing when the
segmented-schema geometry bug shipped: the geometry resolved to all-NaN, the fit's
SVD never converged, but the only test touching the pipeline (`_fit_quality`)
swallowed the exception. These tests assert the pipeline produces *finite* output.
"""

from __future__ import annotations

import numpy as np
import pytest

from magnetics.service import nodes


def _all_finite_grid(node):
    z = np.asarray(node["z"], dtype=float)
    return np.all(np.isfinite(z))


def test_qs_fit_returns_a_finite_contour(synthetic_shot):
    node = nodes.build_node(synthetic_shot, "qs_fit")
    assert node["kind"] == "contour"
    assert _all_finite_grid(node), "qs_fit contour has non-finite cells (NaN geometry?)"


@pytest.mark.parametrize(
    "node_id", ["phi_t", "chi_sq_t", "amplitude", "phase_t", "svd_energy", "svd_condition"]
)
def test_qs_timeseries_are_finite(synthetic_shot, node_id):
    node = nodes.build_node(synthetic_shot, node_id)
    assert node["kind"] in ("contour", "line")
    if node["kind"] == "line":
        for s in node["series"]:
            assert np.all(np.isfinite(np.asarray(s["y"], dtype=float)))
    else:
        assert _all_finite_grid(node)


def test_sensor_geometry_extents_finite_for_synthetic_shot(synthetic_shot):
    """The direct regression guard: the QS geometry must not be NaN. Reverting
    omfit_compat.sensor_geometry to the flat `sensors[c]["r"]` read makes every
    extent NaN and this fails (as the fit's SVD then does)."""
    from magnetics.core import qs_device as oc

    geo = oc.sensor_geometry("DIII-D", shot=int(synthetic_shot))
    for coord in ("r_end1", "z_end1", "phi_end1", "theta_end1"):
        vals = np.asarray(geo[coord].values, dtype=float)
        assert np.all(np.isfinite(vals)), f"{coord} has NaNs"


def test_fit_quality_reports_a_real_fit_not_the_fallback(synthetic_shot):
    """With a QS-capable shot, fit_quality returns the real fit metrics (χ² field),
    not the geometry-only fallback — proving the pipeline ran, not just survived."""
    node = nodes.build_node(synthetic_shot, "fit_quality")
    labels = {f["label"] for f in node["fields"]}
    assert any("χ²" in lab or "chi" in lab.lower() for lab in labels), labels


def test_bandpass_cutoff_changes_the_prepared_signal(synthetic_shot):
    """cutoff_lo/cutoff_hi are already wired end to end (nodes.py -> qs_prep.prepare's
    cutoff_hz); a narrower band should visibly change the filtered signal, not just be
    accepted and ignored."""
    wide = nodes._prep_qs_ds(synthetic_shot, {"cutoff_lo": "5.0", "cutoff_hi": "250.0"})
    narrow = nodes._prep_qs_ds(synthetic_shot, {"cutoff_lo": "5.0", "cutoff_hi": "20.0"})
    wide_signal = wide.prepared["signal"].values
    narrow_signal = narrow.prepared["signal"].values
    assert wide_signal.shape == narrow_signal.shape
    assert not np.allclose(wide_signal, narrow_signal)


def test_qs_fit_recovers_injected_mode_amplitudes(synthetic_shot):
    """Correctness, not just finiteness: the synthetic shot injects two rotating
    modes whose *midplane* footprint is a (near-)pure n=1 pattern (amplitude 1.0)
    plus a pure n=2 pattern (0.6). Two facts make the fit a clean toroidal
    decomposition: (a) the generator places the ``Bp_LFS_midplane`` sensors at
    θ≈0 (``diiid.real_theta_of``), so MODE1's poloidal m=1 term contributes
    negligibly to the injected signal; (b) the default fit basis is ms=(0,), whose
    ``exp(-i·nφ)`` harmonics are θ-independent — so the sensors' SLCONTOUR mounting
    θ (``theta_end1``≈5.7°) never enters the projection. The SVD spatial fit must
    recover that: power lands on n=1 and n=2 in the injected ratio, and the
    unforced n=3 basis mode stays spurious (the ~6% ratio error comes from the
    non-orthogonal discrete φ sampling + the seeded noise floor). This inverts a
    genuinely different operation (least-squares over the sensor geometry) than the
    forward model that generated the signals, so agreement is a real check on the
    fit — not a tautology.

    Guards the gap the finiteness tests above leave open: a *wrong-but-finite* fit
    (mode power on the wrong n, or n=3 leakage) passes those and fails this. Note
    the ratio cancels any uniform mis-scaling, so a global-amplitude regression is
    out of scope here."""
    from synthetic_shot import _MODE1, _MODE2

    node = nodes.build_node(synthetic_shot, "amplitude")
    # Time-mean amplitude per fitted mode (|coeff| oscillates as the mode rotates;
    # the mean is the stable envelope). Default fit basis is ns=(1,2,3), ms=(0,).
    amp = {s["name"]: float(np.mean(s["y"])) for s in node["series"]}
    assert set(amp) == {"n=1", "n=2", "n=3"}, amp

    # n=1 and n=2 carry essentially all the power; the unforced n=3 is negligible.
    assert amp["n=3"] < 0.1 * amp["n=2"], f"n=3 not spurious: {amp}"

    # The recovered amplitude ratio tracks the injected ratio (1.0 / 0.6). The
    # noise is seeded, so this is deterministic; the tolerance covers SVD/BLAS drift.
    injected_ratio = _MODE1.amp / _MODE2.amp
    recovered_ratio = amp["n=1"] / amp["n=2"]
    assert recovered_ratio == pytest.approx(injected_ratio, rel=0.2), (
        f"recovered n=1/n=2 ratio {recovered_ratio:.3f} != injected {injected_ratio:.3f}"
    )
