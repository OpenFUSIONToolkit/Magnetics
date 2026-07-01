"""The pure quasi-stationary port (`core/quasistationary.py`) — previously a test
desert. Covers modal recovery, the helicity sign-flip, and the fit↔reconstruct
round-trip.

Sign-convention note (audit follow-up): `quasistationary.reconstruct_grid` uses
`exp(+i(nφ+mθ))` while `qs_bridge._reconstruct_grid` uses `exp(-i…)`. These are
NOT in conflict — each matches its own pipeline's fit basis, and each round-trips
(this file proves it for the pure port; `test_qs_bridge` + `qs_fit` cover the
other). Do not "align" the signs without also flipping the matching fit basis.
"""

from __future__ import annotations

import numpy as np

from magnetics.core import quasistationary as qs

# 8 midplane sensors evenly spaced in φ, tiny toroidal extent.
_PHI = np.linspace(0, 360, 8, endpoint=False)
_P1, _P2 = _PHI - 0.5, _PHI + 0.5
_TH = np.zeros_like(_PHI)
_T_MS = np.linspace(0, 10, 20)


def _locked_signal(n):
    patt = np.cos(np.deg2rad(n * _PHI))
    return patt, np.tile(patt[:, None], (1, _T_MS.size))


def test_recovers_a_locked_mode():
    _, signal = _locked_signal(2)
    res = qs.fit(_T_MS, signal, _P1, _P2, _TH, _TH, ns=(1, 2, 3), ms=(0,))
    amps = {(int(n), int(m)): abs(c) for n, m, c in zip(res.ns, res.ms, res.coeffs[:, 0])}
    assert amps[(2, 0)] > 0.9  # n=2 dominant
    assert amps[(1, 0)] < 1e-6 and amps[(3, 0)] < 1e-6  # others ~zero
    assert np.isfinite(res.condition_number)
    assert float(np.asarray(res.red_chi_sq)[0]) < 1e-9  # noiseless → perfect fit


def test_helicity_flips_poloidal_sign():
    _, signal = _locked_signal(2)
    minus = qs.fit(_T_MS, signal, _P1, _P2, _TH, _TH, ns=(2,), ms=(1,), helicity=-1)
    plus = qs.fit(_T_MS, signal, _P1, _P2, _TH, _TH, ns=(2,), ms=(1,), helicity=+1)
    assert list(minus.ms) == [-1]
    assert list(plus.ms) == [1]


def test_m0_not_flipped_by_helicity():
    _, signal = _locked_signal(2)
    for hel in (-1, 1):
        res = qs.fit(_T_MS, signal, _P1, _P2, _TH, _TH, ns=(1, 2, 3), ms=(0,), helicity=hel)
        assert list(res.ms) == [0, 0, 0]


def test_fit_reconstruct_roundtrip():
    patt, signal = _locked_signal(2)
    res = qs.fit(_T_MS, signal, _P1, _P2, _TH, _TH, ns=(1, 2, 3), ms=(0,))
    recon = qs.reconstruct_grid(res, _PHI, np.array([0.0]), t_idx=0)[0]
    np.testing.assert_allclose(recon, patt, atol=1e-9)
