#!/usr/bin/env python3
"""naver-auto 웹 대시보드 — API + React 빌드 서빙."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local")

STATIC_DIR = ROOT / "web" / "static"
FRONTEND_DIR = ROOT / "frontend"


def ensure_frontend_built() -> None:
    index = STATIC_DIR / "index.html"
    if index.exists():
        return
    if not (FRONTEND_DIR / "package.json").exists():
        print("frontend/ 없음 — React UI를 빌드할 수 없습니다.")
        sys.exit(1)
    print("React UI 빌드 중 (npm run build)…")
    subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True)


def main() -> int:
    import uvicorn

    from naver_auto.web.app import app

    ensure_frontend_built()
    host = "127.0.0.1"
    port = 8787
    print(f"naver-auto UI → http://{host}:{port}")
    print("개발 모드: 터미널1 `naver-auto ui` + 터미널2 `cd frontend && npm run dev`")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
