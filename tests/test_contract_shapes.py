"""Smoke tests for the mock seam: every generator emits the CONTRACT.md shapes.

Imports only magnetics.service.mock (numpy), not the FastAPI app — so these run
with the core install, no `service` extra needed.
"""

from magnetics.service import mock


def test_machines_have_required_fields():
    assert mock.MACHINES
    assert all({"id", "label", "device"} <= set(m) for m in mock.MACHINES)


def test_geometry_is_single_final_frame():
    frames = mock.geometry_frames("MOCK-A", {})
    assert len(frames) == 1
    progress, data = frames[0]
    assert progress == 1.0
    assert {"sensors", "arrays"} <= set(data)
    s = data["sensors"][0]
    assert {"name", "phi", "theta", "r", "z", "kind", "family"} <= set(s)


def test_mock_geometry_reads_the_device_table_not_a_snapshot():
    # Mock positions must resolve through the shot-aware device table (the single
    # source of geometry truth) — not a hardcoded copy. Spot-check one sensor's
    # (r, z, θ) against diiid at mock's reference shot, and require it to be real.
    from magnetics.data import diiid
    from magnetics.service.mock import _GEOM_REF_SHOT

    sensors = mock.geometry_frames("MOCK-A", {})[0][1]["sensors"]
    s = next(x for x in sensors if x["r"] is not None)
    ref = diiid.sensor(s["name"], _GEOM_REF_SHOT)
    assert ref["r"] is not None  # genuinely came from the table
    assert s["r"] == ref["r"] and s["z"] == ref["z"]
    assert s["theta"] == ref["theta"]  # real, table-derived θ


def test_qs_fit_refines_coarse_to_fine():
    frames = mock.qs_fit_frames("MOCK-A", {})
    progs = [p for p, _ in frames]
    assert progs == sorted(progs) and progs[-1] == 1.0  # monotonic, ends at 1
    data = frames[-1][1]
    assert {"contour", "sensors", "modes", "quality"} <= set(data)
    c = data["contour"]
    assert len(c["z"]) == len(c["theta"])  # z is row-major [theta][phi]
    assert len(c["z"][0]) == len(c["phi"])
    # grid gets finer across frames
    assert len(frames[-1][1]["contour"]["phi"]) > len(frames[0][1]["contour"]["phi"])


def test_spectrogram_has_all_panels():
    data = mock.spectrogram_frames("MOCK-A", {})[-1][1]
    assert {"spectrogram", "n_map", "phase_fit", "coherence"} <= set(data)
    sp = data["spectrogram"]
    assert len(sp["power"]) == len(sp["f_kHz"])
    assert len(sp["power"][0]) == len(sp["t_ms"])
