import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Magnetics Analysis Service")

# Allow CORS for React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPO_ROOT = Path(__file__).resolve().parents[4]
MOCK_DIR = REPO_ROOT / "gui" / "web" / "public" / "mock"

@app.get("/api/machines")
async def get_machines():
    path = MOCK_DIR / "machines.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="machines.json not found")
    with open(path, "r") as f:
        return json.load(f)

@app.get("/api/node/{machine}/{nodeId}")
async def get_node(machine: str, nodeId: str, time: float | None = None):
    path = MOCK_DIR / machine / f"{nodeId}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Node {nodeId} for machine {machine} not found")
    
    with open(path, "r") as f:
        node_data = json.load(f)

    # For phase_fit, if the time is specified, we can optionally offset or add mock dynamic behavior.
    if nodeId == "phase_fit" and time is not None:
        # Simulate slight dynamic change to show the backend is alive and calculating!
        # e.g., shift phases slightly based on time
        if "points" in node_data:
            shift = (time * 0.05) % 360
            for pt in node_data["points"]:
                pt["y"] = (pt["y"] + shift) % 360
        if "fit" in node_data and node_data["fit"]:
            shift = (time * 0.05) % 360
            node_data["fit"]["y"] = [(y + shift) % 360 for y in node_data["fit"]["y"]]

    return node_data
