#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

command -v node >/dev/null || { echo "Node.js 22+ is required." >&2; exit 1; }

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null || ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  for candidate in python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
"$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' || { echo "Python 3.10+ is required (or set PYTHON_BIN)." >&2; exit 1; }

npm install
if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
  "$PYTHON_BIN" -m venv --clear .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env — add GOOGLE_VISION_API_KEY before the first real search."
fi

echo "ProofFace setup complete. Run: npm run dev:all"
