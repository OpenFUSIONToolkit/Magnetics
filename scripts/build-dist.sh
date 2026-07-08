#!/usr/bin/env bash
#
# Build the distributable wheel + sdist with the GUI bundled inside the package.
#
# `uv build` alone does NOT build the frontend — the GUI must be compiled and
# staged into src/magnetics/service/webapp/ first, or the wheel ships with no UI.
# This script does the staging dance, builds both artifacts, and verifies the GUI
# and device data actually made it in. This mirrors .github/workflows/release.yml.
#
#   scripts/build-dist.sh            # build into ./dist
#   scripts/build-dist.sh --smoke    # also install the wheel in a temp venv and boot it
#
# Prereqs: Node.js 22 + uv.

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

SMOKE=0
[ "${1:-}" = "--smoke" ] && SMOKE=1

echo "▶ building the GUI (production, same-origin)…"
# No VITE_API_BASE on purpose: a production build with none set serves the API at
# same-origin (relative /api/… URLs), which is what the packaged app needs.
( cd gui/web && npm ci && npm run build )

echo "▶ staging the built GUI into the package (src/magnetics/service/webapp)…"
rm -rf src/magnetics/service/webapp
cp -r gui/web/dist src/magnetics/service/webapp

echo "▶ building sdist + wheel (uv build)…"
rm -rf dist
uv build

echo "▶ verifying the GUI + device data are bundled…"
# Capture the listings first: piping into `grep -q` lets grep close the pipe on
# first match, which SIGPIPEs the producer and trips `set -o pipefail`.
whl_list="$(unzip -l dist/*.whl)"
grep -q "magnetics/service/webapp/index.html" <<<"$whl_list"
grep -q "magnetics/data/device/diiid.json" <<<"$whl_list"
# uv builds the wheel from the sdist, so the sdist must carry the GUI too.
sdist_list="$(tar -tzf dist/*.tar.gz)"
grep -q "src/magnetics/service/webapp/index.html" <<<"$sdist_list"

echo ""
echo "  ✓ built:"
for f in dist/*; do echo "      $f"; done

if [ "$SMOKE" -eq 1 ]; then
  echo ""
  echo "▶ smoke-testing the wheel in a fresh Python 3.12 venv…"
  smoke="$(mktemp -d)"
  uv venv --python 3.12 "$smoke/venv"
  uv pip install --python "$smoke/venv/bin/python" dist/*.whl
  "$smoke/venv/bin/python" -c "import magnetics; print('  import OK:', magnetics.__version__)"
  # Launch from a non-checkout dir so data_dir() uses the per-user fallback.
  ( cd "$smoke" && "$smoke/venv/bin/magnetics" --no-browser --port 8123 ) &
  svc=$!
  trap 'kill "$svc" 2>/dev/null || true; rm -rf "$smoke"' EXIT
  curl -fsS --retry 20 --retry-connrefused --retry-delay 1 http://127.0.0.1:8123/api/machines >/dev/null
  curl -fsS http://127.0.0.1:8123/ | grep -qi "<title"
  echo "  ✓ wheel installs, imports, boots, and serves the GUI + API"
fi

echo ""
echo "  Next: publish by tagging a release — see docs/RELEASING.md."
