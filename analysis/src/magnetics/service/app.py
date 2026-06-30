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
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..data import h5source
from . import mock, nodes

app = FastAPI(title="magnetics service", version="0.1.0",
              description="Real kind-nodes from fetched shot data, with a MOCK fallback.")

# permissive CORS for the Vite dev server
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

STREAM_DELAY_S = 0.5  # simulate compute time between refinement frames


def _frame(result: str, progress: float, final: bool, data: dict, meta: dict) -> dict:
    return {"type": result, "progress": round(progress, 3), "final": final,
            "meta": meta, "data": data}


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "magnetics-mock", "mock": True}


@app.get("/api/machines")
def machines():
    """Real fetched shots if any HDF5 files are present, else the mock machines."""
    nodes.refresh()  # pick up any file fetched since the service started
    real = nodes.machines()
    return real if real else mock.MACHINES


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


class FetchRequest(BaseModel):
    shot: int
    analysis: str = "both"
    backend: str = "mdsthin"  # mdsthin (default) | toksearch (WIP) | remote (WIP) | auto
    tmin: float | None = None
    tmax: float | None = None
    decimate: int = 1
    username: str | None = None
    password: str | None = None  # fed to ssh via askpass; localhost only, not stored
    duo: str | None = None       # Duo passcode, or "1" for push (default)
    # remote backend overrides (None → fetcher defaults: omega via cybele, conda)
    remote_host: str | None = None
    ssh_jump: str | None = None
    remote_dir: str | None = None
    remote_setup: str | None = None


@app.post("/api/fetch")
def post_fetch(req: FetchRequest) -> dict:
    """Pull a shot live via the toksearch/mdsthin fetcher, then expose it.

    Works where the fetcher works (GA cluster, or laptop with creds/Duo or a
    key-based ssh-config gateway). Offline it returns a clear error and the cached
    shots keep serving.
    """
    h5source._ensure_catalog_on_path()
    try:
        import toksearch_fetch  # repo-root data/ module
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500,
                            detail=f"fetcher unavailable: {exc}") from exc
    # only pass remote overrides the caller actually set, so fetcher defaults hold
    remote_kw = {k: v for k, v in {
        "remote_host": req.remote_host, "ssh_jump": req.ssh_jump,
        "remote_dir": req.remote_dir, "remote_setup": req.remote_setup,
    }.items() if v is not None}
    try:
        out = toksearch_fetch.fetch_shot(
            req.shot, req.analysis, backend=req.backend, username=req.username,
            password=req.password, duo=req.duo,
            tmin=req.tmin, tmax=req.tmax, decimate=req.decimate, **remote_kw)
    except SystemExit as exc:  # fetcher uses sys.exit for missing deps/creds
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400,
                            detail=f"fetch failed: {exc}") from exc
    h5source.refresh()
    return {"ok": True, "shot": str(req.shot), "file": out,
            "machines": nodes.machines()}


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

    return StreamingResponse(event_source(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── single-origin (cluster) deploy: serve the built GUI at / if it exists ──
# Mounted LAST so the /api/* routes above take precedence. Present only after a
# `npm run build` (the `run.sh --prod` path); harmless in dev.
_DIST = Path(__file__).resolve().parents[4] / "gui" / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="gui")


def main() -> None:
    """Console entry point: `uv run --extra service magnetics-service`."""
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
