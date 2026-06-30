"""Regression coverage for the no-account synthetic shot helper."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from magnetics.data import h5source
from magnetics.service import nodes

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from make_synthetic_shot import _build_channels  # noqa: E402
from toksearch_fetch import stream_channels_to_h5  # noqa: E402


def test_synthetic_shot_recovers_default_mode_through_service(tmp_path, monkeypatch):
    """The helper's default n=2 must survive the real HDF5 -> node pipeline."""
    shot = 999998
    n_true = 2
    f_khz = 8.0
    channels = _build_channels(n=n_true, f_khz=f_khz, fs_khz=250.0,
                               dur_ms=40.0, seed=0)
    order = {channel.name: i for i, channel in enumerate(channels)}

    def produce(sink):
        for i in range(0, len(channels), 8):
            sink.put(channels[i:i + 8])

    stream_channels_to_h5(
        str(tmp_path / f"shot_{shot}.h5"),
        shot,
        "both",
        "synthetic",
        compression="lzf",
        tmin=None,
        tmax=None,
        stride=1,
        order=order,
        produce=produce,
        queue_max=4,
    )

    monkeypatch.setenv("MAGNETICS_DATA_DIR", str(tmp_path))
    h5source.refresh()
    nodes.refresh()

    result, probes, delta_phi = nodes._spec_result(str(shot), 0.01, 5)
    assert probes == ("MPI66M307D", "MPI66M340D")
    assert delta_phi == 33.0

    band = (result.frequency >= (f_khz - 0.5) * 1e3) & (
        result.frequency <= (f_khz + 0.5) * 1e3
    )
    band_columns = np.flatnonzero(band)
    peak_in_band = np.unravel_index(
        np.argmax(result.power[:, band]), result.power[:, band].shape
    )
    peak = (peak_in_band[0], band_columns[peak_in_band[1]])
    assert int(result.mode_number[peak]) == n_true

    node = nodes.build_node(
        str(shot),
        "mode_number",
        {"fmin": "7.5", "fmax": "8.5", "slice_duration": "0.01"},
    )
    assert node["kind"] == "heatmap"
    assert node["meta"]["probes"] == ["MPI66M307D", "MPI66M340D"]
    assert node["meta"]["delta_phi_deg"] == 33.0
    f_row = int(np.argmin(np.abs(np.asarray(node["y"]) - f_khz)))
    assert n_true in {int(v) for v in node["z"][f_row]}
