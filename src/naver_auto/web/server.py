"""CLI: naver-auto-ui"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC_DIR = ROOT / "web" / "static"
FRONTEND_DIR = ROOT / "frontend"


def _ensure_built() -> None:
    if (STATIC_DIR / "index.html").exists():
        return
    if not (FRONTEND_DIR / "package.json").exists():
        raise RuntimeError("frontend/ 없음")
    subprocess.run(["npm", "install"], cwd=FRONTEND_DIR, check=True)
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND_DIR, check=True)


def main() -> None:
    import uvicorn

    from naver_auto.web.app import app

    _ensure_built()
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
