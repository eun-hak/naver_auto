"""네이버 글쓰기 에디터 — iframe/mainFrame 탐색."""

from __future__ import annotations

import os
import time
from typing import Union

from playwright.sync_api import Frame, Page

EditorRoot = Union[Page, Frame]

DEFAULT_TITLE_ID = "SE-57e88f24-17c3-43b1-b4c0-b1d82982af49"
DEFAULT_BODY_ID = "SE-7dbd51c2-8472-4b30-815f-e09cf5f57a3c"

PARAGRAPH = ".se-text-paragraph.se-text-paragraph-align-left"
TITLE_SELECTOR = f".se-documentTitle {PARAGRAPH}"
BODY_SELECTOR = f".se-component-content {PARAGRAPH}"

EDITOR_MARKERS = (
    PARAGRAPH,
    ".se-documentTitle",
    ".se-component-content",
    ".se-main-container",
)


def title_element_id() -> str:
    return os.getenv("NAVER_EDITOR_TITLE_ID", DEFAULT_TITLE_ID).strip()


def body_element_id() -> str:
    return os.getenv("NAVER_EDITOR_BODY_ID", DEFAULT_BODY_ID).strip()


def locator_by_id(root: EditorRoot, element_id: str):
    return root.locator(f'[id="{element_id}"]')


def resolve_title_locator(root: EditorRoot):
    """제목 입력 영역 — env id가 만료돼도 DOM 구조로 fallback."""
    env_id = title_element_id()
    if env_id:
        loc = locator_by_id(root, env_id)
        if loc.count() > 0:
            return loc.first
    loc = root.locator(TITLE_SELECTOR).first
    if loc.count() > 0:
        return loc
    loc = root.locator(".se-documentTitle [id^='SE-']").first
    if loc.count() > 0:
        return loc
    return root.locator(PARAGRAPH).first


BODY_PARAGRAPH_SELECTORS = (
    ".se-component.se-text .se-text-paragraph",
    ".se-component-text .se-text-paragraph",
    f".se-component-content {PARAGRAPH}",
)


def body_paragraph_locator(root: EditorRoot):
    """제목 제외 본문 문단 목록 (모바일/데스크톱 공통)."""
    for sel in BODY_PARAGRAPH_SELECTORS:
        loc = root.locator(sel)
        if loc.count() > 0:
            return loc
    return root.locator(BODY_SELECTOR)


def resolve_last_body_paragraph(root: EditorRoot):
    loc = body_paragraph_locator(root)
    if loc.count() > 0:
        return loc.last
    return loc.first


def resolve_body_focus_locator(root: EditorRoot):
    """본문 끝 포커스 — 세션마다 바뀌는 id 대신 구조 기반 탐색."""
    env_id = body_element_id()
    if env_id:
        loc = locator_by_id(root, env_id)
        if loc.count() > 0:
            return loc.last

    loc = body_paragraph_locator(root)
    if loc.count() > 0:
        return loc.last

    for sel in (".se-components-wrap", ".se-main-container", ".se-content"):
        target = root.locator(sel).first
        if target.count() > 0:
            return target

    return root.locator(BODY_SELECTOR).first


def detect_editor_ids(root: EditorRoot) -> tuple[str | None, str | None]:
    title_id: str | None = None
    body_id: str | None = None
    t = root.locator(".se-documentTitle [id^='SE-']").first
    if t.count() > 0:
        title_id = t.get_attribute("id")
    b = root.locator(".se-component.se-text .se-text-paragraph[id^='SE-']").last
    if b.count() > 0:
        body_id = b.get_attribute("id")
    return title_id, body_id


def _has_editor(root: EditorRoot) -> bool:
    if locator_by_id(root, title_element_id()).count() > 0:
        return True
    if locator_by_id(root, body_element_id()).count() > 0:
        return True
    for sel in EDITOR_MARKERS:
        if root.locator(sel).count() > 0:
            return True
    try:
        if root.get_by_text("제목", exact=True).count() > 0:
            return True
    except Exception:
        pass
    return False


def _scan_frames(page: Page) -> EditorRoot | None:
    if _has_editor(page):
        return page
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        if _has_editor(frame):
            return frame
    fr = page.frame(name="mainFrame")
    if fr and _has_editor(fr):
        return fr
    return None


def editor_detected(page: Page) -> bool:
    return _scan_frames(page) is not None


def _blog_id() -> str:
    return (os.getenv("NAVER_BLOG_ID") or os.getenv("NAVER_ID") or "").strip()


def _write_urls() -> list[str]:
    bid = _blog_id()
    return [
        f"https://blog.naver.com/{bid}?Redirect=Write&",
        f"https://blog.naver.com/PostWriteForm.naver?blogId={bid}&Redirect=Write&",
    ]


def find_editor_root(page: Page) -> EditorRoot | None:
    """현재 페이지에서 에디터 탐색 (navigation 없음)."""
    return _scan_frames(page)


def resolve_editor_root(page: Page, *, timeout_sec: int = 60) -> EditorRoot:
    """글쓰기 페이지/iframe에서 Smart Editor ONE 루트 반환."""
    from naver_auto.paths import DEBUG_DIR

    urls = _write_urls()
    deadline = time.time() + timeout_sec
    last_url = page.url

    for url in urls:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        page.goto(url, wait_until="domcontentloaded", timeout=min(int(remaining * 1000), 60000))
        last_url = page.url
        time.sleep(2)

        inner_deadline = time.time() + min(remaining, 45)
        while time.time() < inner_deadline:
            found = _scan_frames(page)
            if found:
                return found
            try:
                page.wait_for_selector("#mainFrame", timeout=3000)
                fr = page.frame(name="mainFrame")
                if fr:
                    fr.wait_for_load_state("domcontentloaded", timeout=10000)
                    if _has_editor(fr):
                        return fr
            except Exception:
                pass
            time.sleep(0.8)

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(DEBUG_DIR / "editor_not_found.png"), full_page=True)
    frames = [f.url for f in page.frames]
    raise RuntimeError(
        "글쓰기 에디터를 찾지 못했습니다.\n"
        f"  URL: {last_url}\n"
        f"  blogId: {_blog_id()}\n"
        f"  frames: {frames[:5]}"
    )


def keyboard_page(page: Page, root: EditorRoot) -> Page:
    """키보드 입력은 항상 최상위 Page에서."""
    if isinstance(root, Frame):
        return root.page
    return page


def editor_keyboard(page: Page, root: EditorRoot):
    return keyboard_page(page, root).keyboard
