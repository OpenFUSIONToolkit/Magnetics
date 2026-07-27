"""Bad-channel exclusion (#56): the store, the API, and the analysis seam.

A misbehaving probe must drop out of *both* analyses from one action, and must
keep rendering (greyed) on the sensor map so the operator can see what they
dropped. The subtle half is caching: several analysis functions are lru_cached,
and an exclusion that changes the answer without changing the cache key would
serve a stale pre-exclusion fit.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from magnetics.data import exclusions
from magnetics.service import app as app_mod
from magnetics.service import nodes

from .conftest import SYNTH_SHOT


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Redirect ONLY the exclusions file to a temp dir.

    Patching ``h5source.data_dir`` would also move the shot-file lookup and hide
    the synthetic fixture shot, so patch the store's own path helper instead.
    """
    monkeypatch.setattr(exclusions, "_path", lambda: tmp_path / "exclusions.json")
    nodes.refresh()
    yield
    nodes.refresh()


class TestStore:
    def test_roundtrip_and_sorting(self):
        assert exclusions.get(SYNTH_SHOT) == []
        stored = exclusions.set_for_shot(SYNTH_SHOT, ["ZZZ", "AAA", "AAA"])
        assert stored == ["AAA", "ZZZ"]  # sorted + de-duplicated
        assert exclusions.get(SYNTH_SHOT) == ["AAA", "ZZZ"]

    def test_blank_and_whitespace_names_are_dropped(self):
        assert exclusions.set_for_shot(SYNTH_SHOT, ["  A  ", "", "   "]) == ["A"]

    def test_clearing_removes_the_shot_entry(self, tmp_path):
        exclusions.set_for_shot(SYNTH_SHOT, ["A"])
        assert exclusions.set_for_shot(SYNTH_SHOT, []) == []
        # no residue left behind for a cleared shot
        assert json.loads((tmp_path / "exclusions.json").read_text()) == {}

    def test_shots_are_independent(self):
        exclusions.set_for_shot(1, ["A"])
        exclusions.set_for_shot(2, ["B"])
        assert exclusions.get(1) == ["A"]
        assert exclusions.get(2) == ["B"]

    def test_int_and_str_shot_ids_are_the_same_key(self):
        exclusions.set_for_shot(184927, ["A"])
        assert exclusions.get("184927") == ["A"]

    def test_corrupt_store_degrades_to_empty(self, tmp_path):
        (tmp_path / "exclusions.json").write_text("{not json")
        assert exclusions.get(SYNTH_SHOT) == []  # never raises into the analysis

    def test_write_is_atomic_leaving_no_temp_files(self, tmp_path):
        exclusions.set_for_shot(SYNTH_SHOT, ["A"])
        assert [p.name for p in tmp_path.iterdir()] == ["exclusions.json"]


class TestParseParam:
    @pytest.mark.parametrize(
        "raw,want",
        [
            ("", ()),
            (None, ()),
            ("A", ("A",)),
            ("B, A", ("A", "B")),  # sorted → stable cache key
            ("A,,A , ", ("A",)),  # de-duplicated, blanks dropped
        ],
    )
    def test_parse(self, raw, want):
        assert exclusions.parse_param(raw) == want


class TestAnalysisSeam:
    """The exclusion has to bite below both analyses, not per view."""

    def test_array_channels_drops_excluded(self):
        before = nodes._array_channels(SYNTH_SHOT, ("MPI_BDOT",))
        assert before, "fixture should have a toroidal array"
        victim = before[0][0]
        exclusions.set_for_shot(SYNTH_SHOT, [victim])
        after = nodes._array_channels(SYNTH_SHOT, ("MPI_BDOT",))
        assert victim not in [n for n, _ in after]
        assert len(after) == len(before) - 1

    def test_every_rotating_helper_inherits_it(self):
        """_toroidal_arr / _pick_pair / _toroidal_grid all resolve channels through
        _array_channels, so one exclusion covers them without per-call plumbing."""
        victim = nodes._toroidal_arr(str(SYNTH_SHOT))[0][0]
        exclusions.set_for_shot(SYNTH_SHOT, [victim])
        assert victim not in [n for n, _ in nodes._toroidal_arr(str(SYNTH_SHOT))]
        assert victim not in [n for n, _ in nodes._pick_pair(str(SYNTH_SHOT))]

    def test_excluded_channel_still_appears_on_the_sensor_map(self):
        """Dropped from the fits, still drawn — the view greys it so the operator
        can see what was excluded and put it back."""
        victim = nodes._toroidal_arr(str(SYNTH_SHOT))[0][0]
        exclusions.set_for_shot(SYNTH_SHOT, [victim])
        geo = nodes.build_node(str(SYNTH_SHOT), "geometry", {})
        assert victim in geo["meta"]["excluded"]
        assert victim in [p["label"] for p in geo["points"]]

    def test_spectrogram_cache_is_keyed_on_exclusions(self):
        """_spec_result is lru_cached without `names` in its key, but excluding a
        channel can change the probe pair — the key must move or a stale
        pre-exclusion STFT is served."""
        shot = str(SYNTH_SHOT)
        (n1, _), (n2, _) = nodes._pick_pair(shot)
        nodes._spec_result(shot, 0.002, 5, 2000, nodes._excluded(shot))
        exclusions.set_for_shot(SYNTH_SHOT, [n1])
        assert nodes._excluded(shot) == (n1,)
        (m1, _), (m2, _) = nodes._pick_pair(shot)
        assert n1 not in (m1, m2), "excluded probe must not be re-picked"
        # different key → recomputed against the new pair, not the cached one
        res, probes, _ = nodes._spec_result(shot, 0.002, 5, 2000, nodes._excluded(shot))
        assert n1 not in probes

    def test_qs_fit_exclude_unions_the_shot_exclusions(self, monkeypatch):
        """The QS tab's own per-fit deselect and the shot-wide bad-channel list
        must both reach the fit, not override one another."""
        seen = {}

        def _spy(*args, **kwargs):
            seen["fit_exclude"] = kwargs.get("fit_exclude", args[-1] if args else ())
            raise RuntimeError("stop after capturing the cache key")

        _spy.cache_clear = lambda: None  # nodes.refresh() clears the real lru_cache
        monkeypatch.setattr(nodes, "_qs_run", _spy)
        exclusions.set_for_shot(SYNTH_SHOT, ["BADCHAN"])
        with pytest.raises(RuntimeError):
            nodes._prep_qs_ds(str(SYNTH_SHOT), {"fit_exclude": "PANELCHAN"})
        got = seen["fit_exclude"]
        assert any("BADCHAN" in p for p in got), got
        assert any("PANELCHAN" in p for p in got), got


class TestApi:
    def test_get_put_roundtrip(self):
        client = TestClient(app_mod.app)
        r = client.get(f"/api/exclusions/{SYNTH_SHOT}")
        assert r.status_code == 200
        assert r.json() == {"shot": str(SYNTH_SHOT), "excluded": []}

        r = client.put(f"/api/exclusions/{SYNTH_SHOT}", json={"excluded": ["B", "A"]})
        assert r.status_code == 200
        assert r.json()["excluded"] == ["A", "B"]
        assert client.get(f"/api/exclusions/{SYNTH_SHOT}").json()["excluded"] == ["A", "B"]

    def test_put_empty_clears(self):
        client = TestClient(app_mod.app)
        client.put(f"/api/exclusions/{SYNTH_SHOT}", json={"excluded": ["A"]})
        assert (
            client.put(f"/api/exclusions/{SYNTH_SHOT}", json={"excluded": []}).json()["excluded"]
            == []
        )

    def test_missing_body_field_defaults_to_empty(self):
        client = TestClient(app_mod.app)
        assert client.put(f"/api/exclusions/{SYNTH_SHOT}", json={}).status_code == 200
