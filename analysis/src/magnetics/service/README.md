# Magnetics analysis service

Thin FastAPI backend that serves the GUI from the HDF5 files the fetcher
(`data/toksearch_fetch.py`) produces, and can trigger a live pull. Physics lives
in `core/`, device specifics in `data/`; routes here stay thin.

## Endpoints
- `GET  /api/health` — liveness + the data dir in use
- `GET  /api/machines` — one entry per shot file found in the data dir
- `GET  /api/node/{shot}/{node_id}` — a kind-tagged Node for the GUI's `<NodeView>`.
  `node_id` ∈ `geometry` (scatter2d), `spectrogram` (heatmap, real STFT),
  `contour` (raw δBp(φ,t)), `fit_quality` (metrics, real condition number K),
  `phase_fit` (scatter2d + fit).
- `POST /api/fetch` — body `{shot, analysis, backend?, tmin?, tmax?, decimate?}`;
  pulls a fresh shot via the fetcher, then exposes it. Needs GA creds/cluster to
  actually pull; offline it returns a clear error and cached shots keep serving.

## Run it locally (two terminals)

Backend (point it at the repo's `data/` dir, which holds the `*.h5` pulls):
```bash
cd analysis
MAGNETICS_DATA_DIR="$(cd ../data && pwd)" \
  uv run uvicorn magnetics.service.app:app --port 8000 --reload
```

Frontend (the team's GUI), pointed at the backend:
```bash
cd gui/web
npm install
VITE_API_BASE=http://127.0.0.1:8000 npm run dev    # http://localhost:5173
```

Open http://localhost:5173 — the header shows "● live backend", the shot picker
lists the shots in `data/`, **Sensors** shows the φ–θ map, **Rotating** shows a
real STFT spectrogram, and **Fits** shows the real condition number K.

`MAGNETICS_DATA_DIR` defaults to the repo's `data/` dir, so the env var is only
needed if your shot files live elsewhere.

## Pull a shot with no manual copying (`backend: "remote"`)

A new user does **not** rsync anything by hand. The `remote` backend, from your
laptop, opens one authenticated SSH connection to the GA cluster, auto-syncs the
fetcher, runs the toksearch pull where PTDATA is local, and copies the `.h5` back
to `data/datafile/`. In the GUI's **Pull a shot** control pick `remote (run on
cluster)`, or from the CLI:

```bash
uv run python data/toksearch_fetch.py --backend remote --shot 184927 --analysis rotating
```

Defaults: run on `omega` via the `cybele.gat.com` jump host, loading toksearch
with `module purge && module load conda && conda activate toksearch_env`. Override
with `--remote-host / --ssh-jump / --remote-dir / --remote-setup` (or the matching
`/api/fetch` body fields). Auth (password + Duo) is interactive in the terminal
running the fetch — for the GUI that's the **uvicorn** terminal.
