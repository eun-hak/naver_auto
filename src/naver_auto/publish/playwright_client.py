"""Playwright 브라우저 세션 관리."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Frame, Page, sync_playwright

from naver_auto.paths import AUTH_DIR, DEBUG_DIR, storage_state_path
from naver_auto.publish.editor_context import editor_detected, find_editor_root, resolve_editor_root

BROWSER_PROFILE_DIR = AUTH_DIR / "browser_profile"


def blog_id() -> str:
    blog = os.getenv("NAVER_BLOG_ID", "").strip()
    if blog:
        return blog
    login_id = os.getenv("NAVER_ID", "").strip()
    if login_id:
        return login_id
    raise RuntimeError(
        "NAVER_BLOG_ID가 필요합니다. 로그인 ID와 블로그 주소 ID가 다를 수 있습니다. "
        "예: blog.naver.com/ifsae42 → NAVER_BLOG_ID=ifsae42"
    )


def write_url() -> str:
    bid = blog_id()
    return f"https://blog.naver.com/{bid}?Redirect=Write&"


EDITOR_SELECTORS = EDITOR_MARKERS = (
    ".se-documentTitle",
    ".se-title-text",
    "span.se-placeholder",
    ".se-component-content",
    ".se-main-container",
)


def editor_ready(page: Page) -> bool:
    return editor_detected(page)


def wait_for_editor(page: Page, *, timeout_ms: int = 60000) -> Frame | Page:
    from naver_auto.publish.editor_actions import dismiss_popups

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        found = find_editor_root(page)
        if found:
            dismiss_popups(page, root=found)
            return found
        time.sleep(0.4)
    if "nid.naver.com" in page.url:
        raise RuntimeError(
            "네이버 로그인 세션이 만료되었습니다. "
            "`python scripts/login_once.py`로 다시 로그인하세요."
        )
    return resolve_editor_root(page, timeout_sec=min(max(timeout_ms // 1000, 15), 45))


def session_exists() -> bool:
    if BROWSER_PROFILE_DIR.exists() and any(BROWSER_PROFILE_DIR.iterdir()):
        return True
    path = storage_state_path()
    return path.exists() and path.stat().st_size > 0


@contextmanager
def browser_context(*, headless: bool = False) -> Iterator[tuple[Browser | None, BrowserContext]]:
    """영구 브라우저 프로필 사용 — 네이버 세션·캡차 빈도 완화."""
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE_DIR),
                headless=headless,
                viewport={"width": 1400, "height": 900},
                locale="ko-KR",
                args=["--disable-blink-features=AutomationControlled"],
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
            )
        except Exception as exc:
            msg = str(exc)
            if "existing browser session" in msg or "Target page, context or browser has been closed" in msg:
                raise RuntimeError(
                    "네이버 로그인용 브라우저가 아직 열려 있습니다. "
                    "login_once.py로 연 Chrome 창을 모두 닫은 뒤 다시 실행하세요."
                ) from exc
            raise
        try:
            yield context.browser, context
        finally:
            context.close()


def save_debug_screenshot(page: Page, name: str) -> Path:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def save_storage_state(context: BrowserContext) -> Path:
    path = storage_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    return path
