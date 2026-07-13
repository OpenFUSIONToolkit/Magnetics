"""The `magnetics` launcher: port picking, data-dir resolution, arg parsing."""

from __future__ import annotations

import os
import socket

import pytest

from magnetics import cli
from magnetics.data import h5source


def test_free_port_returns_bindable_port():
    port = cli._free_port("127.0.0.1")
    # The returned port must actually be free (bindable right now).
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))


def test_free_port_skips_occupied_start():
    # Occupy `start`; _free_port must step past it.
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        start = busy.getsockname()[1]
        busy.listen()
        port = cli._free_port("127.0.0.1", start=start, tries=50)
        assert port != start
        with socket.socket() as s:
            s.bind(("127.0.0.1", port))


def test_help_exits_clean(capsys):
    # --help must not trigger the deferred heavy imports; argparse exits 0.
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "magnetics GUI" in capsys.readouterr().out  # help text printed


def test_data_dir_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("MAGNETICS_DATA_DIR", str(tmp_path / "shots"))
    assert h5source.data_dir() == (tmp_path / "shots").resolve()


def test_fetch_cli_data_dir_sets_env(tmp_path, monkeypatch):
    # `magnetics-fetch --data-dir X` must set MAGNETICS_DATA_DIR before fetching so
    # the shot lands in X. Stub fetch_shot so we assert the env without a real pull.
    from magnetics.data.fetch import toksearch

    monkeypatch.delenv("MAGNETICS_DATA_DIR", raising=False)
    seen = {}

    def fake_fetch_shot(*args, **kwargs):
        seen["data_dir"] = os.environ.get("MAGNETICS_DATA_DIR")

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    toksearch.main(["--shot", "1", "--data-dir", str(tmp_path / "scratch")])
    assert seen["data_dir"] == str((tmp_path / "scratch").resolve())
    assert h5source.data_dir() == (tmp_path / "scratch").resolve()


def test_data_dir_source_checkout(monkeypatch):
    # In this repo checkout (pyproject.toml + gui/ both present), data_dir() is
    # the repo's data/ dir, not the per-user fallback.
    monkeypatch.delenv("MAGNETICS_DATA_DIR", raising=False)
    d = h5source.data_dir()
    assert d.name == "data"
    assert (d.parent / "pyproject.toml").is_file()
