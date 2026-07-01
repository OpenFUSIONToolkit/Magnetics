#!/usr/bin/env bash
#
# One command to run the GUI.
#
# DEFAULT is LIVE: the GUI talks to the real FastAPI service, and NO mock data is
# served or renderable in this mode. The rotating-mode (MODESPEC) path serves real
# analysis from fetched shots; the quasi-stationary fit stream is still a stub. Use
# `static` only for offline frontend work against the demo fixtures.
#
#   ./run.sh           live    — FastAPI service (:8000) + GUI (:5173) against it (default)
#   ./run.sh static    demo    — GUI on :5173 only, STATIC mock fixtures (no backend)
#   ./run.sh --prod    deploy  — build the GUI and serve it on one port (:8000)
#
# Press Ctrl-C to stop. Prereqs: Node.js 22 + uv (uv only needed for live/--prod).

set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-live}"

echo "▶ ensuring GUI deps (npm)…"
[ -d gui/web/node_modules ] || ( cd gui/web && npm install )

case "$MODE" in
  static|--static|dev)
    echo ""
    echo "  ✓ open  http://localhost:5173   (GUI, hot-reload; STATIC mock fixtures — demo only)"
    echo ""
    cd gui/web
    exec npm run dev
    ;;

  --live|live|"")
    echo "▶ syncing Python deps (uv)…"
    uv sync --extra service --quiet
    echo "▶ starting service (:8000) + GUI dev server (:5173)…"
    uv run --extra service magnetics-service &
    SERVICE_PID=$!
    ( cd gui/web && VITE_API_BASE=http://127.0.0.1:8000 npm run dev ) &
    GUI_PID=$!
    trap 'echo; echo "▶ stopping…"; kill "$SERVICE_PID" "$GUI_PID" 2>/dev/null || true' EXIT INT TERM
    echo ""
    echo "  ✓ open  http://localhost:5173   (GUI LIVE against :8000 — no mock data)"
    echo ""
    wait
    ;;

  --prod|prod)
    echo "▶ syncing Python deps (uv)…"
    uv sync --extra service --quiet
    echo "▶ building GUI…"
    ( cd gui/web && npm run build )
    echo "▶ staging built GUI into the package (magnetics/service/webapp)…"
    rm -rf src/magnetics/service/webapp
    cp -r gui/web/dist src/magnetics/service/webapp
    echo ""
    echo "  ✓ open  http://127.0.0.1:8000   (single origin — GUI served on one port)"
    echo ""
    exec uv run --extra service magnetics-service
    ;;

  *)
    echo "usage: ./run.sh [live | static | --prod]" >&2
    exit 2
    ;;
esac
