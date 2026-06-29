#!/usr/bin/env bash
#
# One command to run the whole app — the analysis service (real fetched-shot data)
# + the GUI, wired together.
#
#   ./run.sh           dev mode — FastAPI on :8000 + Vite dev (hot reload) on :5173
#   ./run.sh --prod    one port — build the GUI; FastAPI serves it on :8000
#
# Press Ctrl-C to stop everything. Prereqs (one-time): uv, Node.js. This script
# syncs all Python + JS packages itself. MAGNETICS_DATA_DIR defaults to ./data
# (where the fetcher writes shots, incl. data/datafile/).

set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
MODE="${1:-dev}"
export MAGNETICS_DATA_DIR="${MAGNETICS_DATA_DIR:-$ROOT/data}"

echo "▶ syncing Python deps (uv)…"
( cd analysis && uv sync --quiet )

echo "▶ ensuring GUI deps (npm)…"
[ -d gui/web/node_modules ] || ( cd gui/web && npm install )

case "$MODE" in
  --prod|prod)
    echo "▶ building GUI…"
    ( cd gui/web && npm run build )
    echo ""
    echo "  ✓ open  http://127.0.0.1:8000   (single origin — GUI + API on one port)"
    echo ""
    cd analysis
    exec uv run uvicorn magnetics.service.app:app --host 0.0.0.0 --port 8000
    ;;

  dev|"")
    echo "▶ starting service (:8000) + GUI dev server (:5173)…"
    ( cd analysis && uv run uvicorn magnetics.service.app:app --port 8000 --reload ) &
    SERVICE_PID=$!
    ( cd gui/web && VITE_API_BASE=http://127.0.0.1:8000 npm run dev ) &
    GUI_PID=$!
    trap 'echo; echo "▶ stopping…"; kill "$SERVICE_PID" "$GUI_PID" 2>/dev/null || true' EXIT INT TERM
    echo ""
    echo "  ✓ open  http://localhost:5173   (GUI, hot-reload; API on :8000)"
    echo ""
    wait
    ;;

  *)
    echo "usage: ./run.sh [--prod]" >&2
    exit 2
    ;;
esac
