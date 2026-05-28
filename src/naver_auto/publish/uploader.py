"""네이버 블로그 Smart Editor ONE 업로드."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_fixed

from naver_auto.image.resolver import resolve_draft_images
from naver_auto.paths import DRAFTS_DIR, load_yaml
from naver_auto.publish.editor_actions import (
    fill_title,
    insert_text,
    log as editor_log,
    publish_live,
    save_draft,
    set_tags,
    switch_to_mobile_preview,
    upload_image,
    wait_editor_ready,
)
from naver_auto.publish.daily_limit import can_publish, record_publish
from naver_auto.publish.naver_login import LOGIN_URL, ensure_naver_login
from naver_auto.publish.playwright_client import (
    browser_context,
    editor_ready,
    save_debug_screenshot,
    session_exists,
    wait_for_editor,
    write_url,
)


IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\(images/(\d+)\.jpg\)")


def _strip_header(body: str) -> str:
    lines = body.splitlines()
    if lines and lines[0].startswith("> "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    return "\n".join(lines)


def _parse_blocks(body: str) -> tuple[str, list[dict[str, Any]]]:
    body = _strip_header(body)
    title = "제목 없음"
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    content = body
    if title != "제목 없음":
        content = re.sub(r"^#\s+.+\n+", "", content, count=1)

    blocks: list[dict[str, Any]] = []
    pos = 0
    for match in IMAGE_MD_RE.finditer(content):
        text_part = content[pos : match.start()].strip()
        if text_part:
            blocks.append({"type": "text", "content": text_part})
        blocks.append({"type": "image", "index": int(match.group(2))})
        pos = match.end()
    tail = content[pos:].strip()
    if tail:
        blocks.append({"type": "text", "content": tail})

    if not blocks and content.strip():
        blocks.append({"type": "text", "content": content.strip()})

    return title, blocks


def upload_draft_on_page(
    page,
    draft_dir: Path,
    *,
    live: bool = False,
    root=None,
) -> str | None:
    """이미 열린 에디터 페이지에서 초안 업로드."""
    meta = json.loads((draft_dir / "meta.json").read_text(encoding="utf-8"))
    body = (draft_dir / "body.md").read_text(encoding="utf-8")
    title, blocks = _parse_blocks(body)
    title = meta.get("title") or title
    images_dir = draft_dir / "images"

    editor_log("에디터 준비 확인…")
    root = wait_editor_ready(page, root=root)

    publish_cfg = load_yaml("publish.yaml")
    if publish_cfg.get("mobile_preview", True):
        switch_to_mobile_preview(page, root)

    fill_title(page, title, root=root)
    time.sleep(0.5)

    editor_log(f"블록 {len(blocks)}개 업로드…")
    for i, block in enumerate(blocks, 1):
        if block["type"] == "text":
            insert_text(page, block["content"], root=root)
        elif block["type"] == "image":
            img_path = images_dir / f"{block['index']:02d}.jpg"
            if img_path.exists():
                editor_log(f"블록 {i}/{len(blocks)}")
                upload_image(page, img_path, root=root)

    set_tags(page, meta.get("tags", ""), root=root)

    mode = "live" if live else publish_cfg.get("publish_mode", "draft")
    if mode == "live" or live:
        publish_live(page, root=root)
    else:
        save_draft(page, root=root)

    url = page.url
    save_debug_screenshot(page, f"upload_{meta.get('draft_id', 'draft')}")
    editor_log("완료")
    return url


def _ensure_editor_page(page) -> None:
    if editor_ready(page):
        try:
            wait_for_editor(page, timeout_ms=15000)
            return
        except RuntimeError:
            pass

    naver_id = os.getenv("NAVER_ID", "").strip()
    password = os.getenv("NAVER_PASSWORD", "").strip()
    if "nid.naver.com" in page.url or not editor_ready(page):
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        result = ensure_naver_login(page, naver_id, password, allow_manual=True)
        if not result.ok:
            raise RuntimeError(f"네이버 로그인 실패: {result.message}")

    wait_for_editor(page, timeout_ms=60000)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(3))
def _upload_to_naver(
    draft_dir: Path,
    *,
    live: bool = False,
) -> str | None:
    with browser_context(headless=False) as (_, context):
        page = context.new_page()
        _ensure_editor_page(page)
        return upload_draft_on_page(page, draft_dir, live=live)


def publish_draft(
    draft_id: str,
    *,
    live: bool = False,
    skip_limit: bool = False,
) -> Path:
    if not session_exists() and not (os.getenv("NAVER_ID") and os.getenv("NAVER_PASSWORD")):
        raise RuntimeError(
            "네이버 세션이 없습니다. `.env`에 NAVER_ID/PASSWORD 설정 후 "
            "`python scripts/login_once.py` 또는 `naver-auto publish`를 실행하세요."
        )

    draft_dir = DRAFTS_DIR / draft_id
    if not draft_dir.exists():
        matches = list(DRAFTS_DIR.glob(f"*{draft_id}*"))
        if not matches:
            raise FileNotFoundError(f"초안 없음: {draft_id}")
        draft_dir = matches[0]

    if not skip_limit:
        ok, msg = can_publish()
        if not ok:
            raise RuntimeError(msg)

    print("[publish] 이미지 확인…", flush=True)
    resolve_draft_images(draft_dir)
    print("[publish] 네이버 업로드…", flush=True)
    url = _upload_to_naver(draft_dir, live=live)

    meta_path = draft_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = "published" if live else "naver_draft"
    meta["naver_url"] = url
    meta["published_at"] = datetime.now(timezone.utc).isoformat()
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    record_publish(meta.get("draft_id", draft_id), mode="live" if live else "draft", url=url)
    return draft_dir
