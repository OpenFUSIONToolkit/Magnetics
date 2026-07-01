"""Shot deletion: the h5source removers + the DELETE /api/machines routes.

Runs against an isolated temp data dir (monkeypatched MAGNETICS_DATA_DIR) so it
never touches the session synthetic shots other tests rely on. Each test clears
the cached index at the end so the restored env is re-globbed cleanly.

Run:  uv run python -m pytest tests/test_delete.py -q
"""

from __future__ import annotations

import h5py
import numpy as np
from fastapi.testclient import TestClient

from magnetics.data import h5source
from magnetics.service import nodes
from magnetics.service.app import app

client = TestClient(app)


def _write_shot(path, shot, nchan=2):
    """Minimal shot file: a `shot` attr + a couple of channel groups."""
    with h5py.File(path, "w") as h5:
        h5.attrs["shot"] = int(shot)
        for i in range(nchan):
            g = h5.create_group(f"CH{i}")
            g.create_dataset("data", data=np.zeros(4, np.float32))
            g["time"] = np.arange(4, dtype=float)


def _use_tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGNETICS_DATA_DIR", str(tmp_path))
    d = tmp_path / "datafile"
    d.mkdir()
    h5source.refresh()
    return d


def test_delete_shot_removes_every_file_for_that_shot(tmp_path, monkeypatch):
    d = _use_tmp_data_dir(tmp_path, monkeypatch)
    # a shot can span two files (e.g. a normal pull + a bench artifact)
    _write_shot(d / "shot_555.h5", 555)
    _write_shot(d / "bench_full_555.h5", 555)
    _write_shot(d / "shot_777.h5", 777)

    removed = h5source.delete_shot(555)

    assert len(removed) == 2
    assert not (d / "shot_555.h5").exists()
    assert not (d / "bench_full_555.h5").exists()
    assert (d / "shot_777.h5").exists()  # a different shot is untouched
    ids = {s["id"] for s in h5source.list_shots()}
    assert ids == {"777"}
    h5source.refresh()


def test_delete_shot_no_match_returns_empty(tmp_path, monkeypatch):
    d = _use_tmp_data_dir(tmp_path, monkeypatch)
    _write_shot(d / "shot_111.h5", 111)

    assert h5source.delete_shot(999) == []
    assert (d / "shot_111.h5").exists()  # nothing deleted on a miss
    h5source.refresh()


def test_delete_all_shots_clears_every_file(tmp_path, monkeypatch):
    d = _use_tmp_data_dir(tmp_path, monkeypatch)
    _write_shot(d / "shot_111.h5", 111)
    _write_shot(d / "shot_222.h5", 222)

    removed = h5source.delete_all_shots()

    assert len(removed) == 2
    assert h5source.list_shots() == []
    assert not any(d.glob("*.h5"))
    h5source.refresh()


def test_delete_route_then_404(tmp_path, monkeypatch):
    d = _use_tmp_data_dir(tmp_path, monkeypatch)
    _write_shot(d / "shot_555.h5", 555)
    nodes.refresh()

    r = client.delete("/api/machines/555")
    assert r.status_code == 200
    body = r.json()
    assert body["removed"] and body["shot"] == "555"
    assert not (d / "shot_555.h5").exists()

    # second delete: nothing left to remove → 404
    assert client.delete("/api/machines/555").status_code == 404
    h5source.refresh()
    nodes.refresh()


def test_delete_all_route(tmp_path, monkeypatch):
    d = _use_tmp_data_dir(tmp_path, monkeypatch)
    _write_shot(d / "shot_1.h5", 111)
    _write_shot(d / "shot_2.h5", 222)
    nodes.refresh()

    r = client.delete("/api/machines")
    assert r.status_code == 200
    assert len(r.json()["removed"]) == 2
    assert not any(d.glob("*.h5"))
    h5source.refresh()
    nodes.refresh()
