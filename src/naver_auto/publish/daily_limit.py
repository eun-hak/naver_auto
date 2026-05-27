"""일일 발행 한도 관리."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from naver_auto.paths import DATA_DIR, load_yaml


def _log_path() -> Path:
    return DATA_DIR / "publish" / "publish_log.json"


def _load_log() -> dict:
    path = _log_path()
    if not path.exists():
        return {"days": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_log(data: dict) -> None:
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_key() -> str:
    return date.today().isoformat()


def count_today() -> int:
    log = _load_log()
    return len(log.get("days", {}).get(today_key(), []))


def daily_limit() -> int:
    cfg = load_yaml("publish.yaml")
    return int(cfg.get("daily_limit", 8))


def can_publish(*, extra: int = 1) -> tuple[bool, str]:
    limit = daily_limit()
    current = count_today()
    if current + extra > limit:
        return False, f"일일 발행 한도 초과 ({current}/{limit})"
    return True, ""


def record_publish(draft_id: str, *, mode: str, url: str | None = None) -> None:
    log = _load_log()
    days = log.setdefault("days", {})
    entries = days.setdefault(today_key(), [])
    entries.append(
        {
            "draft_id": draft_id,
            "mode": mode,
            "url": url,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_log(log)
