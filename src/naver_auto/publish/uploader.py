"""네이버 블로그 Smart Editor ONE 업로드."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyperclip
from tenacity import retry, stop_after_attempt, wait_fixed

from naver_auto.image.resolver import resolve_draft_images
from naver_auto.paths import DRAFTS_DIR, load_yaml
from naver_auto.publish.daily_limit import can_publish, record_publish
from naver_auto.publish.playwright_client import (
    browser_context,
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


def _paste_text(page, text: str) -> None:
    pyperclip.copy(text)
    page.keyboard.press("Meta+V") if _is_mac() else page.keyboard.press("Control+V")
    time.sleep(0.3)


def _is_mac() -> bool:
    import sys

    return sys.platform == "darwin"


def _wait_editor(page) -> None:
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)
    for selector in (
        ".se-documentTitle",
        ".se-title-text",
        "span.se-placeholder",
        ".se-component-content",
    ):
        try:
            page.wait_for_selector(selector, timeout=8000)
            return
        except Exception:
            continue
    raise RuntimeError("에디터 로딩 실패 — storage_state 재로그인 필요")


def _fill_title(page, title: str) -> None:
    selectors = (
        ".se-documentTitle",
        ".se-title-text",
        "div[contenteditable='true'].se-text-paragraph",
    )
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() == 0:
            continue
        loc.click()
        _paste_text(page, title)
        return
    raise RuntimeError("제목 입력 영역을 찾지 못했습니다.")


def _focus_body(page) -> None:
    selectors = (
        ".se-component-content .se-text-paragraph",
        ".se-main-container",
        ".se-section-text",
    )
    for sel in selectors:
        loc = page.locator(sel).first
        if loc.count() == 0:
            continue
        loc.click()
        return
    page.locator("body").click()


def _insert_text_block(page, text: str) -> None:
    plain = _markdown_to_plain(text)
    if not plain.strip():
        return
    _focus_body(page)
    _paste_text(page, plain)
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")


def _markdown_to_plain(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            lines.append(stripped[3:].strip())
            lines.append("")
        elif stripped.startswith("> "):
            lines.append(stripped[2:].strip())
        elif stripped.startswith("- "):
            lines.append(f"• {stripped[2:].strip()}")
        elif stripped.startswith("#"):
            continue
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _upload_image(page, image_path: Path) -> None:
    with page.expect_file_chooser(timeout=10000) as fc_info:
        for sel in (
            "button.se-image-toolbar-button",
            "button[data-name='image']",
            ".se-toolbar-item-image",
        ):
            btn = page.locator(sel).first
            if btn.count() > 0:
                btn.click()
                break
        else:
            page.locator(".se-toolbar").get_by_text("사진").first.click()

    chooser = fc_info.value
    chooser.set_files(str(image_path.resolve()))
    time.sleep(2)


def _set_tags(page, tags: str) -> None:
    if not tags.strip():
        return
    tag_list = [t.strip() for t in re.split(r"[,\s#]+", tags) if t.strip()]
    for sel in ("input#tagInput", "input[name='tag']", ".tag_input__"):
        loc = page.locator(sel).first
        if loc.count() == 0:
            continue
        for tag in tag_list[:10]:
            loc.fill(tag)
            page.keyboard.press("Enter")
            time.sleep(0.2)
        return


def _click_save_draft(page) -> None:
    for sel in (
        "button.save_btn__",
        "button[data-click-area='tpb.save']",
        ".save_btn_area__ button",
    ):
        btn = page.locator(sel).first
        if btn.count() > 0:
            btn.click()
            time.sleep(2)
            return
    page.get_by_role("button", name="임시저장").first.click()
    time.sleep(2)


def _click_publish(page) -> None:
    for sel in (
        "button.publish_btn__",
        "button[data-click-area='tpb.publish']",
    ):
        btn = page.locator(sel).first
        if btn.count() > 0:
            btn.click()
            time.sleep(1)
            confirm = page.get_by_role("button", name="발행").last
            if confirm.count() > 0:
                confirm.click()
            time.sleep(3)
            return
    page.get_by_role("button", name="발행").first.click()
    time.sleep(3)


@retry(stop=stop_after_attempt(2), wait=wait_fixed(3))
def _upload_to_naver(
    draft_dir: Path,
    *,
    live: bool = False,
) -> str | None:
    meta = json.loads((draft_dir / "meta.json").read_text(encoding="utf-8"))
    body = (draft_dir / "body.md").read_text(encoding="utf-8")
    title, blocks = _parse_blocks(body)
    title = meta.get("title") or title
    images_dir = draft_dir / "images"

    with browser_context(headless=False) as (_, context):
        page = context.new_page()
        page.goto(write_url(), wait_until="domcontentloaded", timeout=60000)
        _wait_editor(page)

        _fill_title(page, title)
        time.sleep(0.5)
        _focus_body(page)

        for block in blocks:
            if block["type"] == "text":
                _insert_text_block(page, block["content"])
            elif block["type"] == "image":
                img_path = images_dir / f"{block['index']:02d}.jpg"
                if img_path.exists():
                    _upload_image(page, img_path)

        _set_tags(page, meta.get("tags", ""))

        publish_cfg = load_yaml("publish.yaml")
        mode = "live" if live else publish_cfg.get("publish_mode", "draft")
        if mode == "live" or live:
            _click_publish(page)
        else:
            _click_save_draft(page)

        url = page.url
        save_debug_screenshot(page, f"upload_{meta.get('draft_id', 'draft')}")
        return url


def publish_draft(
    draft_id: str,
    *,
    live: bool = False,
    skip_limit: bool = False,
) -> Path:
    if not session_exists():
        raise RuntimeError(
            "네이버 세션이 없습니다. `python scripts/login_once.py`로 먼저 로그인하세요."
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

    resolve_draft_images(draft_dir)
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
