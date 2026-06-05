"""키워드 txt 큐 → 초안 일괄 생성 (+ 선택: 네이버 임시저장)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from naver_auto.content.generator import create_draft_from_keyword
from naver_auto.image.resolver import resolve_draft_images
from naver_auto.paths import DRAFTS_DIR, KEYWORDS_DONE_LOG, KEYWORDS_QUEUE_FILE, ensure_dirs
from naver_auto.publish.daily_limit import can_publish
from naver_auto.publish.playwright_client import browser_headless
from naver_auto.publish.uploader import publish_draft


@dataclass(frozen=True)
class QueueItem:
    keyword: str
    category: str | None = None
    line_index: int = -1
    raw_line: str = ""


@dataclass
class BatchResult:
    keyword: str
    ok: bool
    draft_id: str | None = None
    published: bool = False
    message: str = ""


def parse_queue_line(line: str, *, line_index: int = -1) -> QueueItem | None:
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    category: str | None = None
    if "|" in stripped:
        kw, cat = stripped.split("|", 1)
        keyword = kw.strip()
        category = cat.strip() or None
    else:
        keyword = stripped
    if not keyword:
        return None
    return QueueItem(
        keyword=keyword,
        category=category,
        line_index=line_index,
        raw_line=raw,
    )


def read_queue(path: Path | None = None) -> list[QueueItem]:
    queue_path = path or KEYWORDS_QUEUE_FILE
    if not queue_path.exists():
        return []
    items: list[QueueItem] = []
    for i, line in enumerate(queue_path.read_text(encoding="utf-8").splitlines()):
        item = parse_queue_line(line, line_index=i)
        if item:
            items.append(item)
    return items


def find_draft_by_keyword(keyword: str) -> Path | None:
    for path in DRAFTS_DIR.iterdir():
        if not path.is_dir() or not (path / "meta.json").exists():
            continue
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        if str(meta.get("keyword", "")).strip() == keyword.strip():
            return path
    return None


def append_done_log(keyword: str, draft_id: str) -> None:
    KEYWORDS_DONE_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with KEYWORDS_DONE_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{ts}\t{keyword}\t{draft_id}\n")


def remove_from_queue(keyword: str, *, path: Path | None = None) -> None:
    queue_path = path or KEYWORDS_QUEUE_FILE
    if not queue_path.exists():
        return
    lines = queue_path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        item = parse_queue_line(line)
        if item and item.keyword.strip() == keyword.strip():
            continue
        if not line.endswith("\n"):
            line = line + "\n"
        kept.append(line)
    queue_path.write_text("".join(kept), encoding="utf-8")


def ensure_queue_template() -> Path:
    ensure_dirs()
    if not KEYWORDS_QUEUE_FILE.exists():
        KEYWORDS_QUEUE_FILE.write_text(
            "# 키워드 한 줄에 하나\n"
            "# 카테고리: 키워드 | 재테크\n"
            "# 실행: naver-auto batch\n"
            "# 생성+네이버: naver-auto batch --publish\n",
            encoding="utf-8",
        )
    return KEYWORDS_QUEUE_FILE


def _try_publish(
    *,
    prefix: str,
    draft_id: str,
    live: bool,
    headless: bool | None = None,
    log: Callable[[str], None],
) -> tuple[bool, str]:
    ok, msg = can_publish()
    if not ok:
        log(f"{prefix} — 네이버 업로드 생략: {msg}")
        return False, msg
    action = "발행" if live else "임시저장"
    mode = "headless" if browser_headless(override=headless) else "Chrome"
    log(f"{prefix} — 네이버 {action} 중… ({mode})")
    publish_draft(draft_id, live=live, headless=headless, log=log)
    log(f"{prefix} — 네이버 {action} 완료")
    return True, f"naver {action}"


def run_keyword_batch(
    *,
    queue_file: Path | None = None,
    default_category: str | None = None,
    limit: int | None = None,
    skip_images: bool = False,
    force: bool = False,
    remove_on_success: bool = True,
    dry_run: bool = False,
    publish: bool = False,
    live: bool = False,
    headless: bool | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[BatchResult]:
    ensure_dirs()
    queue_path = queue_file or ensure_queue_template()
    items = read_queue(queue_path)
    if limit is not None:
        items = items[: max(0, limit)]

    results: list[BatchResult] = []
    if not items:
        return results

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    for i, item in enumerate(items, start=1):
        kw = item.keyword
        cat = item.category or default_category
        prefix = f"[{i}/{len(items)}] {kw}"

        existing = find_draft_by_keyword(kw)
        if existing and not force:
            draft_id = str(
                json.loads((existing / "meta.json").read_text()).get(
                    "draft_id", existing.name
                )
            )
            message = f"skip (exists): {draft_id}"
            published = False
            if publish and not dry_run:
                try:
                    published, pub_msg = _try_publish(
                        prefix=prefix,
                        draft_id=draft_id,
                        live=live,
                        headless=headless,
                        log=log,
                    )
                    if published:
                        message += f" · {pub_msg}"
                except Exception as exc:
                    message += f" · publish 실패: {exc}"
            results.append(
                BatchResult(
                    keyword=kw,
                    ok=True,
                    draft_id=draft_id,
                    published=published,
                    message=message,
                )
            )
            log(f"{prefix} — {message}")
            if remove_on_success:
                remove_from_queue(kw, path=queue_path)
            continue

        if dry_run:
            suffix = " + naver" if publish else ""
            results.append(
                BatchResult(keyword=kw, ok=True, message=f"dry-run{suffix}")
            )
            log(f"{prefix} — dry-run{suffix}")
            continue

        try:
            log(f"{prefix} — 본문 생성 중…")
            out_dir = create_draft_from_keyword(
                kw,
                category=cat,
                progress=log,
            )
            if not skip_images:
                log(f"{prefix} — 이미지 생성 중…")
                resolve_draft_images(out_dir)
            meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
            draft_id = str(meta.get("draft_id", out_dir.name))
            append_done_log(kw, draft_id)
            if remove_on_success:
                remove_from_queue(kw, path=queue_path)

            message = f"{meta.get('char_count', 0)}자"
            published = False
            if publish:
                try:
                    published, pub_msg = _try_publish(
                        prefix=prefix,
                        draft_id=draft_id,
                        live=live,
                        headless=headless,
                        log=log,
                    )
                    if published:
                        message += f" · {pub_msg}"
                    elif pub_msg:
                        message += f" · publish 생략({pub_msg})"
                except Exception as pub_exc:
                    message += f" · publish 실패: {pub_exc}"
                    log(f"{prefix} — 네이버 업로드 실패: {pub_exc}")

            results.append(
                BatchResult(
                    keyword=kw,
                    ok=True,
                    draft_id=draft_id,
                    published=published,
                    message=message,
                )
            )
            log(f"{prefix} — 완료 → {draft_id}")
        except Exception as exc:
            results.append(
                BatchResult(keyword=kw, ok=False, message=str(exc))
            )
            log(f"{prefix} — 실패: {exc}")

    return results
