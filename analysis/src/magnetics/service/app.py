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

from . import mock

app = FastAPI(title="magnetics mock service", version="0.1.0",
              description="MOCK data in the CONTRACT.md shapes — for GUI development.")

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
    return mock.MACHINES


def _unpack_node(result: str, data: dict) -> dict:
    if result in ("spectrogram", "denoised_spectrogram"):
        # Unpack spectrogram heatmap node
        node = dict(data.get(result, {}))
        node["kind"] = "heatmap"
        if "t_ms" in node:
            node["x"] = node.pop("t_ms")
        if "f_kHz" in node:
            node["y"] = node.pop("f_kHz")
        if "power" in node:
            node["z"] = node.pop("power")
        node["axes"] = {"x": "Time (ms)", "y": "f (kHz)", "z": "log power"}
        node["discrete"] = False
        return node
    elif result == "phase_fit":
        # Already a scatter2d node or dict
        return data
    elif result == "geometry":
        node = dict(data)
        node["kind"] = "geometry"
        return node
    elif result == "qs_fit":
        node = dict(data.get("contour", {}))
        node["kind"] = "contour"
        if "phi" in node:
            node["x"] = node.pop("phi")
        if "theta" in node:
            node["y"] = node.pop("theta")
        node["axes"] = {"x": "φ (deg)", "y": "θ (deg)", "z": "δBp (G)"}
        node["overlay"] = {"points": data.get("sensors", []), "symbol": "square"}
        return node
    return data


@app.get("/api/{machine}/{result}")
def one_shot(machine: str, result: str, request: Request):
    """Final frame only (blocking) — for tests, notebooks, and simple consumers."""
    gen_key = "spectrogram" if result == "denoised_spectrogram" else result
    gen = mock.GENERATORS.get(gen_key)
    if gen is None:
        raise HTTPException(404, f"unknown result '{result}'")
    params = dict(request.query_params)
    progress, data = gen(machine, params)[-1]
    return _frame(result, progress, True, data, {"machine": machine, "params": params})


@app.get("/api/node/{machine}/{result}")
def one_shot_node(machine: str, result: str, request: Request):
    """Returns the unpacked node directly for useNode frontend hook."""
    gen_key = "spectrogram" if result == "denoised_spectrogram" else result
    gen = mock.GENERATORS.get(gen_key)
    if gen is None:
        raise HTTPException(404, f"unknown result '{result}'")
    params = dict(request.query_params)
    progress, data = gen(machine, params)[-1]
    return _unpack_node(result, data)


@app.get("/api/{machine}/{result}/stream")
@app.get("/api/node/{machine}/{result}/stream")
async def stream(machine: str, result: str, request: Request):
    """SSE stream of frames, coarse → fine. Last frame has final=true."""
    gen_key = "spectrogram" if result == "denoised_spectrogram" else result
    gen = mock.GENERATORS.get(gen_key)
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
