#!/usr/bin/env bash
#
# One command to run the GUI.
#
# The working GUI runs on STATIC mock data (gui/web/public/mock/) — no backend
# needed. Live streaming from the FastAPI service is a stub for now, behind --live.
#
#   ./run.sh           static  — GUI on :5173, reads static mock data (default)
#   ./run.sh --live    stub    — also start the FastAPI service and point the GUI
#                                 at it (live streaming; currently a stub)
#   ./run.sh --prod    deploy  — build the GUI and serve it on one port (:8000)
#
# Press Ctrl-C to stop. Prereqs: Node.js 22 (and uv, for --live/--prod).

set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-static}"

echo "▶ ensuring GUI deps (npm)…"
[ -d gui/web/node_modules ] || ( cd gui/web && npm install )

case "$MODE" in
  static|dev|"")
    echo ""
    echo "  ✓ open  http://localhost:5173   (GUI, hot-reload; STATIC mock data)"
    echo ""
    cd gui/web
    exec npm run dev
    ;;

  --live|live)
    echo "▶ syncing Python deps (uv)…"
    ( cd analysis && uv sync --extra service --quiet )
    echo "▶ starting service (:8000) + GUI dev server (:5173)…"
    ( cd analysis && uv run --extra service magnetics-service ) &
    SERVICE_PID=$!
    ( cd gui/web && VITE_API_BASE=http://127.0.0.1:8000 npm run dev ) &
    GUI_PID=$!
    trap 'echo; echo "▶ stopping…"; kill "$SERVICE_PID" "$GUI_PID" 2>/dev/null || true' EXIT INT TERM
    echo ""
    echo "  ✓ open  http://localhost:5173   (GUI live against :8000 — live streaming is a stub)"
    echo ""
    wait
    ;;

  --prod|prod)
    echo "▶ syncing Python deps (uv)…"
    ( cd analysis && uv sync --extra service --quiet )
    echo "▶ building GUI…"
    ( cd gui/web && npm run build )
    echo ""
    echo "  ✓ open  http://127.0.0.1:8000   (single origin — GUI served on one port)"
    echo ""
    cd analysis
    exec uv run --extra service magnetics-service
    ;;

  *)
    echo "usage: ./run.sh [--live | --prod]" >&2
    exit 2
    ;;
esac
