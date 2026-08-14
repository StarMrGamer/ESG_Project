#!/usr/bin/env bash
# build.sh — produce a runnable deployment from a fresh clone.
#
#   ./deploy/build.sh
#
# The frontend build output (web/dist) is git-ignored, so a clone has NO UI until this runs:
# server.py mounts web/dist only if the directory exists, and without it you get a working API
# and a 404 on /. That is the single most common way this deploy goes wrong.
#
# Safe to re-run. Does not start anything — see deploy/esg-radar.service.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "==> ESG Radar build in $ROOT"

# --- python -----------------------------------------------------------------
if [ ! -d venv ]; then
  echo "==> creating venv"
  python3 -m venv venv
fi
./venv/bin/pip install --quiet --upgrade pip
./venv/bin/pip install --quiet -r requirements.txt
echo "==> python deps installed"

# --- frontend ---------------------------------------------------------------
if ! command -v npm >/dev/null 2>&1; then
  cat >&2 <<'EOF'
!! npm not found. The UI cannot be built on this machine.
   Either install Node 18+, or build web/dist elsewhere and copy it here:
       (local)  cd web && npm install && npm run build
       (local)  rsync -a web/dist/ user@server:/path/to/ESG_Project/web/dist/
EOF
  exit 1
fi
cd web
npm ci --silent 2>/dev/null || npm install --silent
npm run build
cd "$ROOT"
echo "==> frontend built -> web/dist"

# --- writable paths the app needs at runtime --------------------------------
mkdir -p .cache data/anchors
touch data/watchlist.json 2>/dev/null || true
echo "==> writable paths ready (.cache, data/anchors, data/watchlist.json)"

# --- verification: never ship a build that cannot prove itself --------------
echo "==> running the engine harness"
./venv/bin/python harness.py | tail -3
echo "==> running the offline selftest"
./venv/bin/python selftest.py 2>&1 | tail -2

# --- anchor the current runs so the verification page works out of the box ---
./venv/bin/python anchor.py >/dev/null 2>&1 || true
echo "==> anchor records: $(ls -1 data/anchors/*.json 2>/dev/null | wc -l)"

cat <<'EOF'

Build complete. To run it:

    HOST=127.0.0.1 PORT=8000 ./venv/bin/python server.py

On a public host, read docs/DEPLOY.md FIRST — there is no authentication on any
endpoint, and several of them spend money against DEEPSEEK_API_KEY.
EOF
