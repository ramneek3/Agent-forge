#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Backend tests"
cd "$ROOT/backend"
source .venv/bin/activate 2>/dev/null || true
pytest -q

echo "==> Frontend build"
cd "$ROOT/frontend"
npm run build

echo "OK"
