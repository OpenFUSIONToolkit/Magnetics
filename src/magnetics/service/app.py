"""FastAPI service implementing CONTRACT.md against MOCK data.

Endpoints (see docs/CONTRACT.md):
  GET /api/machines                       → MachineInfo[]
  GET /api/{machine}/{result}             → a single final frame (one-shot)
  GET /api/{machine}/{result}/stream      → SSE stream of frames, coarse → fine

`{result}` ∈ geometry | qs_fit | spectrogram. The frame envelope is
{type, progress, final, meta, data}. Run:

    cd analysis && uv run python -m magnetics.service.app      # → :8000
    # then point the GUI at it:  VITE_API_BASE=http://127.0.0.1:8000 npm run dev
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import time
import uuid
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..data import h5source
from . import export, mock, nodes

logger = logging.getLogger(__name__)

app = FastAPI(
    title="magnetics service",
    version="0.1.0",
    description="Real kind-nodes from fetched shot data, with a MOCK fallback.",
)

# permissive CORS for the Vite dev server
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STREAM_DELAY_S = 0.5  # simulate compute time between refinement frames


def _frame(result: str, progress: float, final: bool, data: dict, meta: dict) -> dict:
    return {
        "type": result,
        "progress": round(progress, 3),
        "final": final,
        "meta": meta,
        "data": data,
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "magnetics-mock", "mock": True}


@app.get("/api/machines")
def machines():
    """Real fetched shots if any HDF5 files are present, else the mock machines."""
    # Re-index the data dir only — do NOT call nodes.refresh(), which also clears the
    # shared per-shot STFT caches (~100 MB/shot). The shot list just needs the file
    # index; blowing away the caches here forces a full STFT rebuild on the next node
    # request after every /api/machines poll (startup, post-pull, manual refresh).
    h5source.refresh()
    real = nodes.machines()
    return real if real else mock.MACHINES


@app.get("/api/devices")
def devices():
    """List device configs (data/device/*.json) + their sensor-set names, so the GUI
    can offer device + sensor-set selection for a pull. `id` is the --device value;
    `sensor_sets` are the names selectable as --sensor-set (composites included)."""
    from ..data import devices as devcfg

    out = []
    for path in sorted(devcfg.DEVICE_DIR.glob("*.json")):
        try:
            d = json.loads(path.read_text())
        except Exception:  # noqa: BLE001 — skip an unparseable device file
            continue
        if "name" not in d or "sensor_sets" not in d:
            continue  # not a device file (e.g. kstar_mirnov_config.json)
        conn = d.get("connection") or {}
        out.append(
            {
                "id": path.stem,  # e.g. "diiid" → --device diiid
                "name": d.get("name", path.stem),  # e.g. "DIII-D"
                "default_shot": d.get("default_shot"),  # per-device example shot
                "sensor_sets": list(d.get("sensor_sets", {}).keys()),
                # `access` = "mdsplus_tree" for NSTX/KSTAR-style devices whose sensors
                # live in an MDSplus tree: those pull ONLY via mdsthin + a named
                # sensor_set (no cluster/remote path, no analysis→signal map).
                "access": d.get("access", "ptdata"),
                # remote (cluster) backend is available only when the device file has
                # a network.cluster block (DIII-D omega); NSTX/KSTAR have none.
                "remote_capable": bool((d.get("network", {}) or {}).get("cluster")),
                # a `connection` block means a device-specific VPN+SSH transport
                # (KSTAR): the GUI collects creds + shows the site note.
                "needs_ssh_creds": bool(d.get("connection")),
                "connect_note": conn.get("note"),
            }
        )
    return out


@app.get("/api/node/{shot}/{node_id}")
def node(shot: str, node_id: str, request: Request):
    """A single bare kind-node built from real fetched shot data — the REST shape
    the GUI's useNode() consumes (data → core → contract). 404 if the shot/node
    isn't available, 422 if the data can't support that analysis."""
    try:
        return nodes.build_node(shot, node_id, dict(request.query_params))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/node/{shot}/{node_id}/download")
def node_download(shot: str, node_id: str, request: Request):
    """The same kind-node as /api/node/... but serialized to an HDF5 file — the
    per-plot "Download data" button. Query params are forwarded (and recorded in the
    file) so the download matches exactly what's on screen. 404/422 like node()."""
    params = dict(request.query_params)
    try:
        n = nodes.build_node(shot, node_id, params)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    # A node that built cleanly (200 on /api/node) must never 500 the download with a
    # raw stack trace — the HDF5 writer sits outside the block above, so guard it too.
    try:
        payload = export.node_to_hdf5(shot, node_id, n, params)
    except Exception:  # noqa: BLE001 — serializer failure → clean 500, logged server-side
        logger.exception("HDF5 export failed for shot %s node %s", shot, node_id)
        raise HTTPException(500, f"could not serialize node '{node_id}' to HDF5")
    filename = f"shot_{shot}_{node_id}.h5"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/x-hdf5",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/channels/{shot}")
def channels(shot: str):
    """Per-shot channel diagnostic: which fetched pointnames each analysis consumes,
    and which are idle (droppable from the pull). 404 if the shot isn't available."""
    try:
        return nodes.channel_usage(shot)
    except KeyError:
        # The underlying KeyError embeds the server's data_dir() path; don't leak it.
        logger.warning("channel_usage: shot %s not available", shot, exc_info=True)
        raise HTTPException(404, f"shot {shot} not found")


class FetchRequest(BaseModel):
    shot: int
    analysis: str = "both"
    backend: str = "mdsthin"  # mdsthin (default) | toksearch (WIP) | remote (WIP) | auto
    tmin: float | None = None
    tmax: float | None = None
    decimate: int = 1
    username: str | None = None
    password: str | None = None  # fed to ssh via askpass; localhost only, not stored
    duo: str | None = None  # Duo passcode, or "1" for push (default)
    # KSTAR two-step auth: VPN login (username/password above) + a separate nkstar
    # SSH login here. localhost only, not stored.
    ssh_user: str | None = None
    ssh_password: str | None = None
    # signal selection (None → fetcher defaults: device "diiid", analysis groups)
    device: str | None = None  # data/device/<device>.json
    sensor_set: str | None = None  # a set under the device's sensor_sets; overrides analysis
    # remote backend overrides (None → device file's network.cluster block: explicit
    # omega.gat.com host + auto cybele ProxyJump + env python — no ssh-config alias)
    remote_host: str | None = None
    ssh_jump: str | None = None
    remote_dir: str | None = None
    remote_python: str | None = None


# ── background fetch jobs (so /api/fetch returns instantly and the GUI can show a
#    real per-channel progress bar instead of a blind elapsed timer) ────────────
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _job_set(jid: str, **kw) -> None:
    with _JOBS_LOCK:
        if jid in _JOBS:
            _JOBS[jid].update(kw)


def _job_get(jid: str) -> dict | None:
    with _JOBS_LOCK:
        return dict(_JOBS[jid]) if jid in _JOBS else None


@app.post("/api/fetch")
def post_fetch(req: FetchRequest) -> dict:
    """Start a live pull in the background; returns {job_id}. Stream its progress
    at GET /api/fetch/{job_id}/stream. Works where the fetcher works (laptop with
    creds/Duo or a key-based ssh-config gateway, or the cluster); offline the job
    reports a clear error and cached shots keep serving."""
    try:
        from ..data.fetch import toksearch
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"fetcher unavailable: {exc}") from exc
    # only pass overrides that are set, so the fetcher's own defaults apply
    # otherwise (e.g. device "diiid", analysis-group selection).
    fetch_kw = {
        k: v
        for k, v in {
            "device": req.device,
            "sensor_set": req.sensor_set,
            "remote_host": req.remote_host,
            "ssh_jump": req.ssh_jump,
            "remote_dir": req.remote_dir,
            "remote_python": req.remote_python,
        }.items()
        if v is not None
    }

    jid = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[jid] = {
            "progress": 0.0,
            "msg": "starting",
            "status": "running",
            "result": None,
            "error": None,
        }

    def on_progress(frac, msg):
        _job_set(jid, progress=float(frac), msg=str(msg))

    def work():
        try:
            out = toksearch.fetch_shot(
                req.shot,
                req.analysis,
                backend=req.backend,
                username=req.username,
                password=req.password,
                duo=req.duo,
                ssh_user=req.ssh_user,
                ssh_password=req.ssh_password,
                tmin=req.tmin,
                tmax=req.tmax,
                decimate=req.decimate,
                progress=on_progress,
                **fetch_kw,  # ty: ignore[invalid-argument-type]
            )
            h5source.refresh()
            nodes.refresh()
            _job_set(
                jid,
                status="done",
                progress=1.0,
                msg="done",
                result={
                    "ok": True,
                    "shot": str(req.shot),
                    "file": out,
                    "machines": nodes.machines(),
                },
            )
        except SystemExit as exc:  # fetcher sys.exit for missing deps/creds
            _job_set(jid, status="error", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            _job_set(jid, status="error", error=f"fetch failed: {exc}")

    threading.Thread(target=work, daemon=True).start()
    return {"job_id": jid}


@app.get("/api/fetch/{job_id}")
def fetch_status(job_id: str) -> dict:
    job = _job_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return job


@app.get("/api/fetch/{job_id}/stream")
def fetch_stream(job_id: str) -> StreamingResponse:
    if _job_get(job_id) is None:
        raise HTTPException(status_code=404, detail="unknown job")

    def gen():
        last = None
        while True:
            job = _job_get(job_id)
            if job is None:
                yield f"data: {json.dumps({'status': 'error', 'error': 'job lost'})}\n\n"
                return
            frame = {"progress": job["progress"], "msg": job["msg"], "status": job["status"]}
            if job["status"] == "done":
                frame["result"] = job["result"]
                yield f"data: {json.dumps(frame)}\n\n"
                return
            if job["status"] == "error":
                frame["error"] = job["error"]
                yield f"data: {json.dumps(frame)}\n\n"
                return
            if frame != last:
                yield f"data: {json.dumps(frame)}\n\n"
                last = frame
            time.sleep(0.25)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/{machine}/{result}")
def one_shot(machine: str, result: str, request: Request):
    """Final frame only (blocking) — for tests, notebooks, and simple consumers."""
    gen = mock.GENERATORS.get(result)
    if gen is None:
        raise HTTPException(404, f"unknown result '{result}'")
    params = dict(request.query_params)
    progress, data = gen(machine, params)[-1]
    return _frame(result, progress, True, data, {"machine": machine, "params": params})


@app.get("/api/{machine}/{result}/stream")
async def stream(machine: str, result: str, request: Request):
    """SSE stream of frames, coarse → fine. Last frame has final=true."""
    gen = mock.GENERATORS.get(result)
    if gen is None:
        raise HTTPException(404, f"unknown result '{result}'")
    params = dict(request.query_params)
    frames = gen(machine, params)
    meta = {"machine": machine, "params": params}

    async def event_source():
        for i, (progress, data) in enumerate(frames):
            if await request.is_disconnected():
                break
            final = i == len(frames) - 1
            payload = _frame(result, progress, final, data, meta)
            yield f"data: {json.dumps(payload)}\n\n"
            if not final:
                await asyncio.sleep(STREAM_DELAY_S)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── single-origin (cluster) deploy: serve the built GUI at / if it exists ──
def _webapp_dir() -> Path | None:
    """Locate the built GUI to serve, or None if it hasn't been built.

    Prefers the copy bundled as package data (``magnetics/service/webapp/``,
    staged from gui/web/dist at build time) so an installed wheel serves the app;
    falls back to the repo's gui/web/dist for a source checkout (run.sh --prod).
    """
    bundled = resources.files("magnetics.service") / "webapp"
    if (bundled / "index.html").is_file():
        return Path(str(bundled))
    dev = Path(__file__).resolve().parents[3] / "gui" / "web" / "dist"
    return dev if (dev / "index.html").is_file() else None


# Mounted LAST so the /api/* routes above take precedence. Present only after a
# frontend build (bundled into the wheel, or gui/web/dist in a source checkout).
_DIST = _webapp_dir()
if _DIST is not None:
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="gui")


def main() -> None:
    """Console entry point: `uv run --extra service magnetics-service`."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
