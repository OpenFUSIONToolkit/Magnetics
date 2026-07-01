"""Service-node HDF5-attr helpers: the `'*'` whole-shot sentinel handling that,
when it regressed, crashed the entire QS path on `float('*')`."""

from __future__ import annotations

import math

import numpy as np

from magnetics.service import nodes


def test_num_attr_parses_or_none():
    assert nodes._num_attr("*") is None  # whole-shot sentinel
    assert nodes._num_attr(None) is None
    assert nodes._num_attr("3.5") == 3.5
    assert nodes._num_attr(np.float64(5.0)) == 5.0
    assert nodes._num_attr(1000) == 1000.0


def test_shot_window_ms_falls_back_to_data_span_on_sentinel(synthetic_shot):
    # The synthetic shot writes tmin/tmax='*'; _shot_window_ms must not blow up and
    # must return the actual data span instead.
    import h5py

    from magnetics.data import h5source

    path = h5source.shot_file(synthetic_shot)
    with h5py.File(str(path), "r") as f:
        assert f.attrs["tmin"] == "*"  # sentinel present
        lo, hi = nodes._shot_window_ms(f)
    assert math.isfinite(lo) and math.isfinite(hi) and hi > lo
