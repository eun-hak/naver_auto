#!/usr/bin/env bash
# 실행: ./scripts/dev.sh
# 윈도우 : .\scripts\dev.ps1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# WSL on Windows drive: use Windows Python/npm (avoid rollup/linux mismatch)
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && [[ "$ROOT" == /mnt/* ]]; then
  echo "WSL detected — launching via PowerShell (Windows venv + npm)..."
  exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ROOT/scripts/dev.ps1"
fi

if [ -f "$ROOT/.venv/Scripts/naver-auto.exe" ]; then
  NAVER_AUTO="$ROOT/.venv/Scripts/naver-auto.exe"
  NPM="npm.cmd"
  export PATH="$ROOT/.venv/Scripts:$PATH"
elif [ -f "$ROOT/.venv/bin/naver-auto" ]; then
  NAVER_AUTO="$ROOT/.venv/bin/naver-auto"
  NPM="npm"
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
else
  echo "naver-auto not found. Run: pip install -e ." >&2
  exit 1
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "frontend npm install..."
  (cd "$ROOT/frontend" && $NPM install)
fi

cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in $(jobs -p); do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Backend:  http://127.0.0.1:8787"
"$NAVER_AUTO" ui --dev &
BACKEND_PID=$!

echo "Frontend: http://127.0.0.1:5173"
(cd "$ROOT/frontend" && $NPM run dev) &
FRONTEND_PID=$!

echo ""
echo "Open: http://127.0.0.1:5173"
echo "Stop: Ctrl+C"
echo ""

wait "$BACKEND_PID" "$FRONTEND_PID"