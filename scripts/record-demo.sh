#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -f .env ]; then
  echo "Missing .env. Run ./scripts/setup.sh and add GOOGLE_VISION_API_KEY." >&2
  exit 1
fi

echo "Pre-flight checks"
curl -fsS http://127.0.0.1:8546/health >/dev/null || { echo "Chain service is not running. Start npm run dev:all." >&2; exit 1; }
curl -fsS http://127.0.0.1:8000/api/health >/dev/null || { echo "Pipeline API is not running. Start npm run dev:all." >&2; exit 1; }
curl -fsS http://localhost:3000/ >/dev/null || { echo "Frontend is not running. Start npm run dev:all." >&2; exit 1; }

echo "All services are ready. Open http://localhost:3000 and begin the unedited recording."
