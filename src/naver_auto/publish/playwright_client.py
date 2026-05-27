"""Playwright 브라우저 세션 관리."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from naver_auto.paths import DEBUG_DIR, storage_state_path


def blog_id() -> str:
    value = os.getenv("NAVER_BLOG_ID", "").strip() or os.getenv("NAVER_ID", "").strip()
    if not value:
        raise RuntimeError("NAVER_BLOG_ID 또는 NAVER_ID 환경변수가 필요합니다.")
    return value


def write_url() -> str:
    return f"https://blog.naver.com/PostWriteForm.naver?blogId={blog_id()}&Redirect=Write"


def session_exists() -> bool:
    path = storage_state_path()
    return path.exists() and path.stat().st_size > 0


@contextmanager
def browser_context(*, headless: bool = False) -> Iterator[tuple[Browser, BrowserContext]]:
    state = storage_state_path()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context_kwargs: dict = {
            "viewport": {"width": 1400, "height": 900},
            "locale": "ko-KR",
        }
        if state.exists():
            context_kwargs["storage_state"] = str(state)
        context = browser.new_context(**context_kwargs)
        try:
            yield browser, context
        finally:
            context.close()
            browser.close()


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
