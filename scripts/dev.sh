#!/usr/bin/env bash
# Frontend (Vite 5173) + Backend (FastAPI 8787)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
elif [ -f ".venv/Scripts/activate" ]; then
  source ".venv/Scripts/activate"
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "frontend npm install..."
  npm install --prefix frontend
fi

cleanup() {
  echo ""
  echo "Shutting down..."
  jobs -p | xargs -r kill 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Backend:  http://127.0.0.1:8787"
naver-auto ui --dev &
BACKEND_PID=$!

echo "Frontend: http://127.0.0.1:5173"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo ""
echo "Open: http://127.0.0.1:5173"
echo "Stop: Ctrl+C"
echo ""

wait "$BACKEND_PID" "$FRONTEND_PID"