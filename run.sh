#!/usr/bin/env bash
#
# One command to run the whole app — the mock analysis service + the GUI, wired
# together. This is also how it runs on a cluster: a single entry point that
# brings up the program and prints a URL to open (forward that one port).
#
#   ./run.sh           dev mode  — FastAPI on :8000 + Vite dev (hot reload) on :5173
#   ./run.sh --prod    cluster   — build the GUI, FastAPI serves it on :8000 (ONE port)
#
# Press Ctrl-C to stop everything.
#
# Prereqs (one-time): uv (https://docs.astral.sh/uv), Node.js 22. This script
# installs/syncs all Python + JS packages itself.

set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-dev}"

echo "▶ syncing Python deps (uv)…"
( cd analysis && uv sync --extra service --quiet )

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
    exec uv run --extra service magnetics-service
    ;;

  dev|"")
    echo "▶ starting service (:8000) + GUI dev server (:5173)…"
    ( cd analysis && uv run --extra service magnetics-service ) &
    SERVICE_PID=$!
    ( cd gui/web && VITE_API_BASE=http://127.0.0.1:8000 npm run dev ) &
    GUI_PID=$!
    trap 'echo; echo "▶ stopping…"; kill "$SERVICE_PID" "$GUI_PID" 2>/dev/null || true' EXIT INT TERM
    echo ""
    echo "  ✓ open  http://localhost:5173   (GUI, hot-reload; API proxied to :8000)"
    echo ""
    wait
    ;;

  *)
    echo "usage: ./run.sh [--prod]" >&2
    exit 2
    ;;
esac
