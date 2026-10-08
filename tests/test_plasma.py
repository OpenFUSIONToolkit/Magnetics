"""Ip flattop detection (core.plasma.ip_flattop) on synthetic current traces."""

import numpy as np
import pytest

from magnetics.core.plasma import ip_flattop


def _shot(sign=1.0, spike=False, dip=False):
    t = np.arange(0.0, 5000.0, 0.5)  # ms
    ip = np.interp(t, [0, 1500, 4300, 4450, 5000], [0, 1.0e6, 1.0e6, 0, 0])
    if spike:
        ip[np.searchsorted(t, 800.0)] = 5.0e6  # one-sample glitch during ramp-up
    if dip:
        ip[(t > 2500) & (t < 2520)] *= 0.8  # brief dip inside the flattop
    return t, sign * ip


def test_finds_ramp_up_and_ramp_down_edges():
    ft = ip_flattop(*_shot())
    assert ft.t_start_ms == pytest.approx(1500 * 0.95, abs=15)  # 95 % on the ramp-up
    assert ft.t_end_ms == pytest.approx(4300 + 150 * 0.05, abs=15)  # start of ramp-down
    assert ft.ip_peak == pytest.approx(1.0e6, rel=0.01)


def test_sign_agnostic_spike_robust_and_dips_do_not_split():
    base = ip_flattop(*_shot())
    for kw in ({"sign": -1.0}, {"spike": True}, {"dip": True}):
        ft = ip_flattop(*_shot(**kw))
        assert ft.t_end_ms == pytest.approx(base.t_end_ms, abs=5), kw
        assert ft.t_start_ms == pytest.approx(base.t_start_ms, abs=5), kw


def test_rejects_empty_or_zero_current():
    with pytest.raises(ValueError):
        ip_flattop(np.array([0.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        ip_flattop(np.arange(10.0), np.zeros(10))
