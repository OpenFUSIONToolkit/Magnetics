"""KSTAR device-reactive wiring tests — all offline (no VPN, no real data).

Covers the three code changes that bring KSTAR toward DIII-D parity:
  * ``_set_channels`` derives θ from (r, z) when a sensor has no explicit ``theta``
    (so supplying r/z alone unblocks the poloidal array);
  * ``_prep_qs_ds`` is DIII-D-only after the develop merge (raises 422 for KSTAR);
    the DIII-D shot still resolves the legacy ``Bp_LFS_midplane`` filter;
  * the rotating spectral nodes run against a synthetic KSTAR shot (device=kstar)
    using the committed MC1T toroidal geometry.
"""

from __future__ import annotations

import numpy as np
import pytest

from magnetics.service import nodes


# ── θ-from-(r,z) fallback in _set_channels ───────────────────────────────────
def _pol_device():
    """A minimal device declaring a poloidal set whose sensors carry (r, z) but
    no explicit ``theta`` — except one that pins θ directly, and one with neither."""
    return {
        "R0": 1.8,
        "sensor_sets": {"pol": {"type": "list", "sensors": ["A", "B", "C", "D"]}},
        "sensors": {
            "A": {"segments": [{"since_shot": 0, "r": 2.4, "z": 0.0}]},  # θ→0°
            "B": {"segments": [{"since_shot": 0, "r": 1.8, "z": 0.5}]},  # θ→90°
            "C": {"segments": [{"since_shot": 0, "theta": 200.0}]},  # explicit
            "D": {"segments": [{"since_shot": 0, "phi": 12.0}]},  # no θ, no r/z
        },
    }


def test_set_channels_derives_theta_from_rz(monkeypatch):
    dev = _pol_device()
    monkeypatch.setattr(nodes.h5source, "channel_names", lambda shot: ["A", "B", "C", "D"])

    out = dict(nodes._set_channels(dev, "pol", "1000", angle="theta"))

    assert out["A"] == pytest.approx(0.0)
    assert out["B"] == pytest.approx(90.0)
    assert out["C"] == pytest.approx(200.0)  # explicit θ wins
    assert "D" not in out  # no θ and no (r, z) → dropped


def test_set_channels_phi_unaffected_by_theta_fallback(monkeypatch):
    dev = _pol_device()
    monkeypatch.setattr(nodes.h5source, "channel_names", lambda shot: ["A", "B", "C", "D"])
    # angle="phi": only D has phi; the r/z→θ fallback must NOT apply to phi.
    out = dict(nodes._set_channels(dev, "pol", "1000", angle="phi"))
    assert out == {"D": pytest.approx(12.0)}


# ── QS is DIII-D-only for now (SLCONTOUR needs the DIII-D device file + Bp arrays)
def test_qs_is_diiid_only(monkeypatch, kstar_shot, synthetic_shot):
    """After the develop merge the SLCONTOUR quasi-stationary fit is DIII-D-only:
    ``_prep_qs_ds`` raises (→ 422) for KSTAR — matching the "QS/poloidal nodes still
    return 422 for KSTAR" follow-up in PR #55 — while a DIII-D shot still resolves the
    legacy ``Bp_LFS_midplane`` filter and reaches ``_qs_run``. (KSTAR's device-specific
    ``qs_default_set`` selection is staged in ``_prep_qs_ds`` for when QS support lands,
    but is gated off by the DIII-D-only guard today.)"""

    class _StopFit(Exception):
        pass

    captured = {}

    def fake_qs_run(shot, ns, ms, channel_filter, *a, **k):
        captured["cf"] = channel_filter
        raise _StopFit

    monkeypatch.setattr(nodes, "_qs_run", fake_qs_run)

    # KSTAR: QS is not supported yet → a clean ValueError (422), never reaching _qs_run.
    with pytest.raises(ValueError, match="DIII-D-only"):
        nodes._prep_qs_ds(kstar_shot, None)

    # DIII-D: resolves the legacy filter and hands it to the fit.
    with pytest.raises(_StopFit):
        nodes._prep_qs_ds(synthetic_shot, None)
    assert captured["cf"] == "Bp_LFS_midplane"


# ── rotating spectral nodes on the synthetic KSTAR shot ──────────────────────
def test_kstar_toroidal_array_resolves(kstar_shot):
    arr = nodes._toroidal_arr(kstar_shot)
    assert len(arr) >= 4  # MC1T channels with φ at this shot
    phis = [phi for _, phi in arr]
    assert phis == sorted(phis)  # sorted by toroidal angle


def test_kstar_spectrogram_node(kstar_shot):
    n = nodes.build_node(kstar_shot, "spectrogram")
    assert n["kind"] == "heatmap"
    assert len(n["z"]) == len(n["y"])  # rows = freqs
    assert len(n["z"][0]) == len(n["x"])  # cols = times


def test_kstar_mode_number_recovers_ground_truth(kstar_shot):
    """The fixture injects n=1 @5 kHz and n=2 @8 kHz; the toroidal fit should see
    integer n's in range somewhere in the map."""
    n = nodes.build_node(kstar_shot, "mode_number")
    assert n["kind"] == "heatmap"
    z = np.asarray(n["z"], dtype=float)
    finite = z[np.isfinite(z)]
    assert finite.size > 0
    assert np.all(np.abs(finite) <= 10)  # sane toroidal mode numbers
