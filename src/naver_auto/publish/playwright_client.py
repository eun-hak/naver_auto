"""Playwright 브라우저 세션 관리."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from playwright.sync_api import Browser, BrowserContext, Frame, Page, sync_playwright

from naver_auto.paths import AUTH_DIR, DEBUG_DIR, load_yaml, storage_state_path
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


def write_urls() -> list[str]:
    """글쓰기 페이지 URL 후보 (우선순위 순)."""
    override = os.getenv("NAVER_WRITE_URL", "").strip()
    if override:
        return [override]
    bid = blog_id()
    return [
        f"https://blog.naver.com/{bid}?Redirect=Write&",
        f"https://blog.naver.com/PostWriteForm.naver?blogId={bid}&Redirect=Write&",
    ]


def write_url() -> str:
    return write_urls()[0]


def _dismiss_chrome_password_prompt(page: Page) -> None:
    for label in ("사용하지 않음", "저장하지 않음", "나중에"):
        btn = page.locator(f'button:has-text("{label}")').first
        if btn.count() > 0:
            try:
                btn.click(timeout=1500)
                time.sleep(0.3)
                return
            except Exception:
                pass


def _on_blog_portal(page: Page) -> bool:
    url = page.url
    return "section.blog.naver.com" in url or "BlogHome.naver" in url


def _write_page_reached(page: Page) -> bool:
    """실제 글쓰기 화면인지 (블로그 홈 URL 오판 방지)."""
    if _on_blog_portal(page):
        return False
    if "nid.naver.com" in page.url:
        return False
    if find_editor_root(page):
        return True
    url = page.url
    return "PostWriteForm" in url or "Redirect=Write" in url


def _poll_editor(page: Page, *, seconds: float = 4.0) -> Frame | Page | None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        found = find_editor_root(page)
        if found:
            return found
        time.sleep(0.2)
    return None


def goto_write_page(
    page: Page,
    *,
    log: Callable[[str], None] | None = None,
    fast: bool = True,
) -> None:
    """로그인 직후·발행 시 글쓰기 에디터 URL로 강제 이동."""
    from naver_auto.publish.editor_context import wait_write_page

    def _log(msg: str) -> None:
        if log:
            log(msg)

    _dismiss_chrome_password_prompt(page)
    bid = blog_id()
    urls = write_urls()
    if len(urls) == 1:
        urls.append(
            f"https://blog.naver.com/PostWriteForm.naver?blogId={bid}&Redirect=Write&"
        )

    for url in urls:
        _log(f"글쓰기 이동: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            wait_write_page(page, fast=fast)
            _dismiss_chrome_password_prompt(page)
            if _write_page_reached(page) or _poll_editor(page, seconds=3.0):
                _log(f"글쓰기 페이지 도달: {page.url}")
                return
        except Exception as exc:
            _log(f"이동 실패 ({url}): {exc}")

    if _on_blog_portal(page):
        _log("블로그 홈 → 글쓰기 버튼 클릭 시도")
        for target in (
            page.locator(f'a[href*="blogId={bid}"][href*="PostWriteForm"]'),
            page.locator(f'a[href*="blog.naver.com/{bid}"][href*="Write"]'),
            page.get_by_role("link", name="글쓰기"),
            page.get_by_role("button", name="글쓰기"),
            page.locator('a[href*="PostWriteForm"]'),
            page.locator('a[href*="Redirect=Write"]'),
        ):
            if target.count() == 0:
                continue
            try:
                target.first.click(timeout=5000)
                time.sleep(0.6)
                wait_write_page(page, fast=fast)
                if _write_page_reached(page) or _poll_editor(page, seconds=3.0):
                    return
            except Exception:
                continue

    save_debug_screenshot(page, "write_page_stuck")
    raise RuntimeError(
        f"글쓰기 페이지로 이동하지 못했습니다. 현재 URL: {page.url}\n"
        f"  .env NAVER_BLOG_ID={blog_id()} (예: ifsae42)\n"
        f"  또는 NAVER_WRITE_URL=https://blog.naver.com/ifsae42?Redirect=Write&"
    )


EDITOR_SELECTORS = EDITOR_MARKERS = (
    ".se-documentTitle",
    ".se-title-text",
    "span.se-placeholder",
    ".se-component-content",
    ".se-main-container",
)


def editor_ready(page: Page) -> bool:
    return editor_detected(page)


def wait_for_editor(
    page: Page,
    *,
    timeout_ms: int = 25000,
    log: Callable[[str], None] | None = None,
) -> Frame | Page:
    from naver_auto.publish.editor_actions import dismiss_popups

    if _on_blog_portal(page):
        goto_write_page(page, log=log, fast=True)

    found = _poll_editor(page, seconds=timeout_ms / 1000)
    if found:
        dismiss_popups(page, root=found)
        return found
    if "nid.naver.com" in page.url:
        raise RuntimeError(
            "네이버 로그인 세션이 만료되었습니다. "
            "`python scripts/login_once.py`로 다시 로그인하세요."
        )
    return resolve_editor_root(page, timeout_sec=min(max(timeout_ms // 1000, 10), 20))


def open_editor_page(
    page: Page,
    *,
    allow_manual: bool = True,
    log: Callable[[str], None] | None = None,
) -> Frame | Page:
    """글쓰기 에디터까지 이동 — login_once.py와 동일한 순서."""
    import os

    from naver_auto.publish.editor_actions import dismiss_popups
    from naver_auto.publish.naver_login import LOGIN_URL, ensure_naver_login

    def _log(msg: str) -> None:
        if log:
            log(msg)

    naver_id = os.getenv("NAVER_ID", "").strip()
    password = os.getenv("NAVER_PASSWORD", "").strip()

    from naver_auto.paths import reload_project_env

    reload_project_env()
    _log(f"블로그 ID: {blog_id()} → {write_url()}")

    has_session = session_exists()
    _log("글쓰기 페이지 바로 이동…")
    try:
        goto_write_page(page, log=_log, fast=True)
    except RuntimeError as exc:
        _log(str(exc))

    root = _poll_editor(page, seconds=5.0 if has_session else 3.0)
    if root:
        dismiss_popups(page, root=root)
        _log("에디터 확인 (로그인 생략)")
        return root

    if "nid.naver.com" not in page.url and not _on_blog_portal(page):
        root = _poll_editor(page, seconds=4.0)
        if root:
            dismiss_popups(page, root=root)
            _log("에디터 확인")
            return root

    if not naver_id or not password:
        raise RuntimeError(
            "네이버 세션이 없습니다. `.env`에 NAVER_ID/PASSWORD 설정 후 "
            "`python scripts/login_once.py`를 실행하세요."
        )

    _log("로그인 중…")
    if "nid.naver.com" not in page.url:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    result = ensure_naver_login(
        page, naver_id, password, allow_manual=allow_manual, fast=True
    )
    if not result.ok:
        raise RuntimeError(f"네이버 로그인 실패: {result.message}")
    _log(result.message)

    goto_write_page(page, log=_log, fast=True)
    root = _poll_editor(page, seconds=8.0)
    if root:
        dismiss_popups(page, root=root)
        _log("에디터 확인")
        return root
    root = wait_for_editor(page, timeout_ms=20000, log=_log)
    dismiss_popups(page, root=root)
    _log("에디터 확인 (wait)")
    return root


def session_exists() -> bool:
    if BROWSER_PROFILE_DIR.exists() and any(BROWSER_PROFILE_DIR.iterdir()):
        return True
    path = storage_state_path()
    return path.exists() and path.stat().st_size > 0


def _env_truthy(name: str) -> bool | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def browser_headless(*, override: bool | None = None) -> bool:
    """Playwright headless 여부 — CLI/env/publish.yaml 순."""
    if override is not None:
        return override
    env = _env_truthy("NAVER_HEADLESS")
    if env is not None:
        return env
    cfg = load_yaml("publish.yaml")
    return bool(cfg.get("headless", False))


@contextmanager
def browser_context(*, headless: bool | None = None) -> Iterator[tuple[Browser | None, BrowserContext]]:
    """영구 브라우저 프로필 사용 — 네이버 세션·캡차 빈도 완화."""
    use_headless = browser_headless(override=headless)
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_PROFILE_DIR),
                headless=use_headless,
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
