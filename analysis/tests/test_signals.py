#!/usr/bin/env python3
"""
Offline tests for the analysis-type signal downselection (no network/deps).

Run:  uv run python -m pytest tests/test_signals.py -q
"""

from __future__ import annotations

from magnetics.data import signals as ms


def test_quasi_stationary_uses_integrated_not_bdot():
    sigs = set(ms.signals_for("quasi-stationary"))
    # integrated Bp + saddle loops present
    assert "MPID66M020" in sigs
    assert "ISLD66M017" in sigs
    # raw bdot probes excluded (those are the rotating-mode workhorse)
    assert not any(pt.endswith("D") and pt.startswith("MPI66M") for pt in sigs)
    assert "MPI66M307D" not in sigs


def test_rotating_uses_bdot_not_integrated():
    sigs = set(ms.signals_for("rotating"))
    # raw dB/dt probes present
    assert "MPI66M307D" in sigs
    # integrated Bp and saddle loops excluded
    assert "MPID66M020" not in sigs
    assert "ISLD66M017" not in sigs


def test_both_is_union_of_all_groups():
    both = set(ms.signals_for("both"))
    union = set().union(*ms.GROUPS.values())
    assert both == union
    # and it is a superset of each single-analysis set
    assert set(ms.signals_for("quasi-stationary")) <= both
    assert set(ms.signals_for("rotating")) <= both


def test_no_duplicates_and_order_preserved():
    for analysis in ms.ANALYSES:
        sigs = ms.signals_for(analysis)
        assert len(sigs) == len(set(sigs)), f"dupes in {analysis}"


def test_reduction_policy():
    # decimation safe for spatial slices, unsafe for FFT-based analyses
    assert ms.decimate_allowed("quasi-stationary") is True
    assert ms.decimate_allowed("rotating") is False
    assert ms.decimate_allowed("both") is False


def test_unknown_analysis_raises():
    import pytest

    with pytest.raises(ValueError):
        ms.signals_for("nonsense")
    with pytest.raises(ValueError):
        ms.decimate_allowed("nonsense")
