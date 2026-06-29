"""FastAPI service: the device boundary for the GUI.

Endpoints (match gui/web/src/lib/api.ts):
  GET  /api/machines                  -> MachineInfo[]
  GET  /api/node/{machine}/{node_id}  -> a kind-tagged Node
  POST /api/fetch                     -> pull a fresh shot (live), then serve it
  GET  /api/health                    -> liveness

Routes are thin: validate, call service.nodes, return the dict. All physics lives
in core/; all device specifics in data/.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..data import h5source
from . import nodes

app = FastAPI(title="Magnetics analysis service", version="0.1.0")

# The Vite dev server runs on 5173; allow it (and the 127.0.0.1 alias) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "data_dir": str(h5source.data_dir())}


@app.get("/api/machines")
def get_machines() -> list[dict]:
    return nodes.machines()


@app.get("/api/node/{machine}/{node_id}")
def get_node(machine: str, node_id: str, request: Request) -> dict:
    params = dict(request.query_params)
    try:
        return nodes.build_node(machine, node_id, params)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # surface the real reason during the hackathon
        raise HTTPException(status_code=500,
                            detail=f"{type(exc).__name__}: {exc}") from exc


class FetchRequest(BaseModel):
    shot: int
    analysis: str = "both"
    backend: str = "auto"
    tmin: float | None = None
    tmax: float | None = None
    decimate: int = 1
    username: str | None = None


@app.post("/api/fetch")
def post_fetch(req: FetchRequest) -> dict:
    """Pull a shot live via the toksearch/mdsthin fetcher, then expose it.

    Works where the fetcher works (GA cluster, or laptop with creds/Duo). Offline
    it returns a clear error and the cached shots keep serving.
    """
    h5source._ensure_catalog_on_path()
    try:
        import toksearch_fetch  # repo-root data/ module
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500,
                            detail=f"fetcher unavailable: {exc}") from exc
    try:
        out = toksearch_fetch.fetch_shot(
            req.shot, req.analysis, backend=req.backend, username=req.username,
            tmin=req.tmin, tmax=req.tmax, decimate=req.decimate)
    except SystemExit as exc:  # fetcher uses sys.exit for missing deps/creds
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400,
                            detail=f"fetch failed: {exc}") from exc
    h5source.refresh()
    return {"ok": True, "shot": str(req.shot), "file": out,
            "machines": nodes.machines()}
