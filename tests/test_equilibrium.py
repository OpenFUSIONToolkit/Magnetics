"""Tests for magnetics.core.equilibrium — q-profile rational surfaces + m anchoring."""

import numpy as np

from magnetics.core.equilibrium import (
    anchor_poloidal_m,
    q_range,
    resonant_surfaces,
)

# a monotonic, physical q-profile: q0 ≈ 1 on axis rising to q_edge ≈ 4.5
PSI = np.linspace(0.0, 1.0, 129)
QPSI = 1.0 + 3.5 * PSI**2  # q(0)=1.0, q(1)=4.5


class TestQRange:
    def test_range(self):
        lo, hi = q_range(QPSI)
        assert abs(lo - 1.0) < 1e-9 and abs(hi - 4.5) < 1e-9

    def test_ignores_nan(self):
        q = QPSI.copy()
        q[10] = np.nan
        lo, hi = q_range(q)
        assert np.isfinite(lo) and np.isfinite(hi)


class TestResonantSurfaces:
    def test_n1_surfaces_are_the_integer_q_values(self):
        # for n=1, q=m/1=m → surfaces at q=2,3,4 (q=1 is the axis endpoint, q=5>qmax)
        surfs = resonant_surfaces(QPSI, PSI, n=1)
        ms = [s.m for s in surfs]
        assert 2 in ms and 3 in ms and 4 in ms
        assert 5 not in ms  # q=5 exceeds q_edge=4.5

    def test_n3_includes_q2_at_m6(self):
        # n=3 → q=m/3; q=2 is the m=6 surface (a 2/1-helicity resonance)
        surfs = resonant_surfaces(QPSI, PSI, n=3)
        by_m = {s.m: s for s in surfs}
        assert 6 in by_m and abs(by_m[6].q - 2.0) < 1e-9
        assert 0.0 <= by_m[6].psi_n <= 1.0  # located on the grid
        # q=1/3 (m=1) is below q_min=1 → no surface
        assert 1 not in by_m

    def test_psi_location_matches_profile(self):
        # q=2.0 for n=1 (m=2): q=1+3.5ψ²=2 → ψ=sqrt(1/3.5)
        surfs = resonant_surfaces(QPSI, PSI, n=1)
        s2 = next(s for s in surfs if s.m == 2)
        assert abs(s2.psi_n - np.sqrt(1.0 / 3.5)) < 2e-2

    def test_zero_n_is_empty(self):
        assert resonant_surfaces(QPSI, PSI, n=0) == []


class TestAnchorPoloidalM:
    def test_rejects_unphysical_alias_and_picks_physical(self):
        # MAC winner m=1 (q=1/3, unphysical for n=3), runner-up m=6 (q=2, physical)
        ms = np.array([-1, 6, -2, 4])
        macs = np.array([0.61, 0.575, 0.558, 0.49])
        res = anchor_poloidal_m(ms, macs, n=3, q_psi=QPSI, psi_n=PSI)
        assert res.raw_m == -1  # what the bare MAC would have said
        assert res.corrected is True
        assert abs(res.chosen_m) == 6 and abs(res.q_surface - 2.0) < 1e-9
        assert res.psi_n is not None and 0.0 <= res.psi_n <= 1.0
        assert 6 in res.allowed_ms and 1 not in res.allowed_ms

    def test_keeps_physical_winner_untouched(self):
        # winner m=6 already resonates → no correction
        ms = np.array([6, -1, 3])
        macs = np.array([0.8, 0.5, 0.4])
        res = anchor_poloidal_m(ms, macs, n=3, q_psi=QPSI, psi_n=PSI)
        assert res.corrected is False and res.chosen_m == 6

    def test_no_physical_alias_leaves_raw(self):
        # tiny plasma q∈[3,4]; for n=3 that needs m∈[9,12]; candidates {1,2} don't resonate
        q = 3.0 + 1.0 * PSI
        ms = np.array([1, 2])
        macs = np.array([0.5, 0.4])
        res = anchor_poloidal_m(ms, macs, n=3, q_psi=q, psi_n=PSI)
        assert res.corrected is False and res.chosen_m == 1  # nothing physical to swap to
        assert res.allowed_ms == []
