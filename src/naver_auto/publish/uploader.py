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
from naver_auto.paths import DRAFTS_DIR, load_yaml, reload_project_env
from naver_auto.publish.editor_actions import (
    fill_title,
    insert_formatted_block,
    insert_subheading,
    log as editor_log,
    publish_live,
    save_draft,
    set_tags,
    switch_to_mobile_preview,
    upload_image,
    wait_editor_ready,
)
from naver_auto.publish.markdown_format import HR_LINE_RE, parse_text_to_blocks
from naver_auto.publish.daily_limit import can_publish, record_publish
from naver_auto.publish.playwright_client import (
    browser_context,
    browser_headless,
    open_editor_page,
    save_debug_screenshot,
    session_exists,
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


def _parse_text_segment(text: str) -> list[dict[str, Any]]:
    """텍스트 덩어리를 소제목·서식 블록으로 분리."""
    blocks: list[dict[str, Any]] = []
    chunk_lines: list[str] = []

    def flush_chunk() -> None:
        if not chunk_lines:
            return
        content = "\n".join(chunk_lines).strip()
        if content:
            blocks.extend(parse_text_to_blocks(content))
        chunk_lines.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            flush_chunk()
            blocks.append({"type": "heading2", "content": stripped[3:].strip()})
        elif stripped.startswith("### "):
            flush_chunk()
            blocks.append({"type": "heading3", "content": stripped[4:].strip()})
        elif stripped.startswith("#"):
            continue
        elif not stripped or HR_LINE_RE.match(stripped):
            flush_chunk()
        else:
            chunk_lines.append(line)
    flush_chunk()
    return blocks


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
            blocks.extend(_parse_text_segment(text_part))
        blocks.append({"type": "image", "index": int(match.group(2))})
        pos = match.end()
    tail = content[pos:].strip()
    if tail:
        blocks.extend(_parse_text_segment(tail))

    if not blocks and content.strip():
        blocks.extend(_parse_text_segment(content.strip()))

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
    formatted_types = {
        "bullet_list",
        "numbered_list",
        "numbered_section",
        "bold_heading",
        "paragraph_group",
        "qa_question",
        "qa_answer",
        "spacer",
    }
    for i, block in enumerate(blocks, 1):
        if block["type"] in formatted_types:
            insert_formatted_block(page, block, root=root)
        elif block["type"] in ("heading2", "heading3"):
            level = 2 if block["type"] == "heading2" else 3
            insert_subheading(page, block["content"], root=root, level=level)
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


def _ensure_editor_page(page, *, allow_manual: bool = True, log=None) -> None:
    open_editor_page(page, allow_manual=allow_manual, log=log)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(3))
def _upload_to_naver(
    draft_dir: Path,
    *,
    live: bool = False,
    allow_manual_login: bool = True,
    headless: bool | None = None,
    log=None,
) -> str | None:
    with browser_context(headless=headless) as (_, context):
        page = context.new_page()
        _ensure_editor_page(page, allow_manual=allow_manual_login, log=log)
        return upload_draft_on_page(page, draft_dir, live=live)


def publish_draft(
    draft_id: str,
    *,
    live: bool = False,
    skip_limit: bool = False,
    allow_manual_login: bool | None = None,
    headless: bool | None = None,
    log=None,
) -> Path:
    use_headless = browser_headless(override=headless)
    if use_headless and not session_exists():
        raise RuntimeError(
            "headless 모드에는 저장된 네이버 세션이 필요합니다. "
            "먼저 `python scripts/login_once.py`로 로그인한 뒤 다시 시도하세요."
        )
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
    reload_project_env()
    mode = "headless" if use_headless else "Chrome"
    print(f"[publish] 네이버 업로드 ({mode})…", flush=True)
    if use_headless:
        allow_manual_login = False
    elif allow_manual_login is None:
        allow_manual_login = os.isatty(0)
    if log:
        log(f"Playwright {mode} 모드")
    url = _upload_to_naver(
        draft_dir,
        live=live,
        allow_manual_login=allow_manual_login,
        headless=use_headless,
        log=log,
    )

    meta_path = draft_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["status"] = "published" if live else "naver_draft"
    meta["naver_url"] = url
    meta["published_at"] = datetime.now(timezone.utc).isoformat()
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    record_publish(meta.get("draft_id", draft_id), mode="live" if live else "draft", url=url)
    return draft_dir
