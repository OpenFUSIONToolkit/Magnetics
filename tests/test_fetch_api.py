"""The live-pull job machinery: POST /api/fetch → background worker → status/SSE.

This is the most stateful, most concurrent code in the service (job registry +
worker thread + progress stream) and the only HTTP surface the GUI's PullControl
talks to. The real fetcher is monkeypatched — no network, no data files written —
so these tests pin the ORCHESTRATION: request forwarding, job lifecycle, error
mapping, cache refresh, and the SSE frame protocol.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from magnetics.data.fetch import toksearch
from magnetics.service import nodes
from magnetics.service.app import app

client = TestClient(app)


def _wait_for(jid, *, until=("done", "error"), timeout=5.0):
    """Poll GET /api/fetch/{jid} until the job leaves 'running' (or timeout)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/fetch/{jid}")
        assert r.status_code == 200
        job = r.json()
        if job["status"] in until:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {jid} still running after {timeout}s: {job}")


def test_post_fetch_happy_path_forwards_request_and_refreshes(monkeypatch, synthetic_shot):
    calls = {}
    refreshed = {"nodes": 0}

    def fake_fetch_shot(shot, analysis, *, progress, **kw):
        calls["shot"], calls["analysis"], calls["kw"] = shot, analysis, kw
        progress(0.5, "pulling")
        return "/tmp/shot_123456.h5"

    real_refresh = nodes.refresh

    def counting_refresh():
        refreshed["nodes"] += 1
        real_refresh()

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    monkeypatch.setattr(nodes, "refresh", counting_refresh)

    r = client.post(
        "/api/fetch",
        json={
            "shot": 123456,
            "analysis": "rotating",
            "backend": "mdsthin",
            "tmin": 1000,
            "tmax": 2000,
            "device": "diiid",
            "sensor_set": "Bp LFS midplane",
        },
    )
    assert r.status_code == 200
    jid = r.json()["job_id"]

    job = _wait_for(jid)
    assert job["status"] == "done"
    assert job["progress"] == 1.0
    # result contract PullControl relies on: shot is a STRING id + fresh machine list
    assert job["result"]["ok"] is True
    assert job["result"]["shot"] == "123456"
    assert job["result"]["file"] == "/tmp/shot_123456.h5"
    assert any(m["id"] == synthetic_shot for m in job["result"]["machines"])
    # the request reached the fetcher with the caller's selection...
    assert calls["shot"] == 123456 and calls["analysis"] == "rotating"
    assert calls["kw"]["backend"] == "mdsthin"
    assert calls["kw"]["tmin"] == 1000 and calls["kw"]["tmax"] == 2000
    assert calls["kw"]["device"] == "diiid"
    assert calls["kw"]["sensor_set"] == "Bp LFS midplane"
    # ...unset optionals were NOT passed (the fetcher's own defaults must apply)
    assert "raw_pointnames" not in calls["kw"]
    # a successful pull must invalidate the node caches (stale-θ regression family)
    assert refreshed["nodes"] == 1


def test_post_fetch_custom_signals_become_raw_pointnames(monkeypatch):
    seen = {}

    def fake_fetch_shot(shot, analysis, *, progress, **kw):
        seen.update(kw)
        return "/tmp/x.h5"

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    r = client.post("/api/fetch", json={"shot": 1, "signals": ["betan", "li"]})
    job = _wait_for(r.json()["job_id"])
    assert job["status"] == "done"
    assert seen["raw_pointnames"] == ["betan", "li"]


@pytest.mark.parametrize(
    "raiser, expect",
    [
        (lambda: (_ for _ in ()).throw(RuntimeError("tunnel died")), "fetch failed: tunnel died"),
        (
            lambda: (_ for _ in ()).throw(SystemExit("Missing dependency: mdsthin")),
            "Missing dependency: mdsthin",
        ),
    ],
)
def test_post_fetch_maps_failures_to_job_error(monkeypatch, raiser, expect):
    def fake_fetch_shot(shot, analysis, *, progress, **kw):
        next(raiser())

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    r = client.post("/api/fetch", json={"shot": 1})
    job = _wait_for(r.json()["job_id"])
    assert job["status"] == "error"
    assert expect in job["error"]
    assert job["result"] is None


def test_fetch_status_unknown_job_404s():
    assert client.get("/api/fetch/nonexistent0").status_code == 404
    assert client.get("/api/fetch/nonexistent0/stream").status_code == 404


def test_progress_callback_updates_job_live(monkeypatch):
    """The worker's progress callback must be visible through GET /api/fetch/{jid}
    while the pull is still running — this is the GUI's per-channel progress bar."""
    release = threading.Event()

    def fake_fetch_shot(shot, analysis, *, progress, **kw):
        progress(0.42, "MPI66M307D")
        assert release.wait(5.0), "test never released the worker"
        return "/tmp/x.h5"

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    r = client.post("/api/fetch", json={"shot": 1})
    jid = r.json()["job_id"]
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            job = client.get(f"/api/fetch/{jid}").json()
            if job["progress"] == 0.42:
                break
            time.sleep(0.02)
        assert job["status"] == "running"
        assert job["progress"] == 0.42 and job["msg"] == "MPI66M307D"
    finally:
        release.set()
    assert _wait_for(jid)["status"] == "done"


def test_stream_emits_terminal_sse_frame(monkeypatch):
    """The SSE stream must emit `data: <json>` frames and terminate with the
    done-frame carrying the result — the exact protocol PullControl's EventSource
    parses."""

    def fake_fetch_shot(shot, analysis, *, progress, **kw):
        return "/tmp/x.h5"

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    r = client.post("/api/fetch", json={"shot": 77})
    jid = r.json()["job_id"]
    _wait_for(jid)  # let it finish so the stream is a single terminal frame

    frames = []
    with client.stream("GET", f"/api/fetch/{jid}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                frames.append(json.loads(line[len("data: ") :]))
    assert frames, "stream produced no data frames"
    last = frames[-1]
    assert last["status"] == "done"
    assert last["progress"] == 1.0
    assert last["result"]["shot"] == "77"


def test_stream_error_frame_carries_the_reason(monkeypatch):
    def fake_fetch_shot(shot, analysis, *, progress, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(toksearch, "fetch_shot", fake_fetch_shot)
    r = client.post("/api/fetch", json={"shot": 1})
    jid = r.json()["job_id"]
    _wait_for(jid, until=("error",))
    with client.stream("GET", f"/api/fetch/{jid}/stream") as resp:
        line = next(ln for ln in resp.iter_lines() if ln.startswith("data: "))
    frame = json.loads(line[len("data: ") :])
    assert frame["status"] == "error"
    assert "boom" in frame["error"]


def test_post_fetch_validation_rejects_missing_shot():
    assert client.post("/api/fetch", json={"analysis": "rotating"}).status_code == 422


def test_job_registry_is_isolated_per_job(monkeypatch):
    """Two jobs must not share state (the registry is a plain dict guarded by a
    lock; a key collision or shared entry would cross progress between pulls)."""

    def ok(shot, analysis, *, progress, **kw):
        return f"/tmp/shot_{shot}.h5"

    def bad(shot, analysis, *, progress, **kw):
        raise RuntimeError("nope")

    monkeypatch.setattr(toksearch, "fetch_shot", ok)
    j1 = client.post("/api/fetch", json={"shot": 1}).json()["job_id"]
    _wait_for(j1)
    monkeypatch.setattr(toksearch, "fetch_shot", bad)
    j2 = client.post("/api/fetch", json={"shot": 2}).json()["job_id"]
    _wait_for(j2, until=("error",))
    assert j1 != j2
    assert client.get(f"/api/fetch/{j1}").json()["status"] == "done"
    assert client.get(f"/api/fetch/{j2}").json()["status"] == "error"
