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
    # Auto-pick a free backend port (prefer 8000) so several checkouts can run at
    # once without colliding. Vite already auto-picks a free GUI port; we just wire
    # the GUI to whichever backend port we grabbed. Override with `PORT=NNNN ./run.sh`.
    PORT="${PORT:-$(python3 - <<'PY'
import socket

def free(p):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        return True
    except OSError:
        return False
    finally:
        s.close()

for p in range(8000, 8100):
    if free(p):
        print(p)
        break
else:  # everything 8000-8099 busy — let the OS pick any free port
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    print(s.getsockname()[1])
    s.close()
PY
)}"
    echo "▶ starting service (:$PORT) + GUI dev server (Vite auto-port)…"
    PORT="$PORT" uv run --extra service magnetics-service &
    SERVICE_PID=$!
    ( cd gui/web && VITE_API_BASE="http://127.0.0.1:$PORT" npm run dev ) &
    GUI_PID=$!
    trap 'echo; echo "▶ stopping…"; kill "$SERVICE_PID" "$GUI_PID" 2>/dev/null || true' EXIT INT TERM
    echo ""
    echo "  ✓ open the GUI URL Vite prints below   (LIVE against :$PORT — no mock data)"
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
