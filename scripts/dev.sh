#!/usr/bin/env bash
#
# 개발 서버 일괄 실행 (Frontend Vite 5173 + Backend FastAPI 8787)
#
# 실행 방법 (프로젝트 루트에서):
#   ./scripts/dev.sh
#
# 실행 권한이 없으면:
#   chmod +x scripts/dev.sh
#   ./scripts/dev.sh
#
# 또는 bash로 직접 실행:
#   bash scripts/dev.sh
#
# 사전 준비:
#   - Python venv (.venv) + pip install -e .
#   - frontend: npm install (없으면 스크립트가 자동 설치)
#   - .env (GEMINI_API_KEY, NVIDIA_API_KEY 등)
#
# 접속: http://127.0.0.1:5173
# 종료: Ctrl+C
#
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