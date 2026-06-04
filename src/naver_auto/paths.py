"""프로젝트 공통 경로."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = Path(__file__).resolve().parents[1]

def reload_project_env() -> None:
    """서버 재시작 없이 .env 변경 반영."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / ".env.local", override=True)


reload_project_env()

CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DRAFTS_DIR = DATA_DIR / "publish" / "drafts"
INBOX_DIR = DATA_DIR / "publish" / "inbox"
KEYWORDS_DIR = DATA_DIR / "keywords"
KEYWORDS_QUEUE_FILE = KEYWORDS_DIR / "queue.txt"
KEYWORDS_DONE_LOG = KEYWORDS_DIR / "done.log"
AUTH_DIR = PROJECT_ROOT / ".auth"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
DEBUG_DIR = PROJECT_ROOT / "debug"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def ensure_dirs() -> None:
    for path in (DRAFTS_DIR, INBOX_DIR, KEYWORDS_DIR, AUTH_DIR, DEBUG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def load_yaml(name: str) -> dict:
    path = CONFIG_DIR / name
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def storage_state_path() -> Path:
    raw = os.getenv("NAVER_STORAGE_STATE", ".auth/storage_state.json")
    path = Path(raw)
    return path if path.is_absolute() else PROJECT_ROOT / path


def naver_api_configured() -> bool:
    return bool(os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"))


def naver_ad_configured() -> bool:
    keys = (
        "NAVER_AD_ACCESS_LICENSE",
        "NAVER_AD_SECRET_KEY",
        "NAVER_AD_CUSTOMER_ID",
    )
    return all(os.getenv(k) for k in keys)
