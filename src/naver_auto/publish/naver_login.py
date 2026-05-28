"""네이버 로그인 — 사람처럼 천천히 입력."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass

from playwright.sync_api import Page

LOGIN_URL = "https://nid.naver.com/nidlogin.login"


@dataclass
class LoginResult:
    ok: bool
    captcha: bool = False
    message: str = ""


def _pause(min_ms: int = 50, max_ms: int = 150) -> None:
    time.sleep(random.uniform(min_ms, max_ms) / 1000)


def captcha_visible(page: Page) -> bool:
    selectors = (
        "#captcha",
        "#captcha_image",
        ".captcha",
        "#chptcha",
        "input[name='chptcha']",
        "#captcha_info",
    )
    for sel in selectors:
        if page.locator(sel).count() > 0:
            return True
    body = page.locator("body").inner_text()
    return "자동입력 방지" in body or "정답을 입력해주세요" in body


def login_error_visible(page: Page) -> bool:
    return page.locator(".error_message, #err_common, .err_msg").count() > 0


def human_type(locator, text: str) -> None:
    """한 글자씩 입력 (붙여넣기 사용 안 함)."""
    locator.click()
    _pause(80, 150)
    for i, ch in enumerate(text):
        locator.press(ch, delay=random.randint(35, 90))
        if i > 0 and random.random() < 0.06:
            _pause(120, 280)


def _login_fast_enabled() -> bool:
    return os.getenv("NAVER_LOGIN_FAST", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _fast_fill_login(page: Page, naver_id: str, password: str) -> LoginResult:
    """fill()로 빠른 로그인 (세션 있을 때 권장)."""
    id_input = page.locator("#id").first
    pw_input = page.locator("#pw").first
    id_input.wait_for(state="visible", timeout=5000)
    id_input.fill(naver_id)
    pw_input.fill(password)
    page.locator("#log\\.login, button.btn_login").first.click()
    try:
        page.wait_for_function(
            "() => !window.location.href.includes('nid.naver.com')",
            timeout=8000,
        )
    except Exception:
        time.sleep(1.2)
    if captcha_visible(page):
        return LoginResult(False, captcha=True, message="캡차 표시됨")
    if "nid.naver.com" not in page.url:
        return LoginResult(True, message="로그인 성공")
    if login_error_visible(page):
        return LoginResult(False, message="아이디·비밀번호 오류 또는 추가 인증 필요")
    return LoginResult(False, message="로그인 페이지에 남아 있음")


def human_login(
    page: Page,
    naver_id: str,
    password: str,
    *,
    fast: bool | None = None,
) -> LoginResult:
    """로그인 페이지에서 아이디·비밀번호 입력."""
    if not naver_id or not password:
        return LoginResult(False, message="NAVER_ID / NAVER_PASSWORD 미설정")

    if "nid.naver.com" not in page.url:
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
        _pause(100, 200)

    if "nid.naver.com" not in page.url:
        return LoginResult(True, message="이미 로그인됨")

    use_fast = _login_fast_enabled() if fast is None else fast
    if use_fast:
        return _fast_fill_login(page, naver_id, password)

    id_input = page.locator("#id").first
    pw_input = page.locator("#pw").first
    id_input.wait_for(state="visible", timeout=5000)

    human_type(id_input, naver_id)
    _pause(80, 150)
    human_type(pw_input, password)
    _pause(100, 200)

    page.locator("#log\\.login, button.btn_login").first.click()
    try:
        page.wait_for_function(
            "() => !window.location.href.includes('nid.naver.com')",
            timeout=8000,
        )
    except Exception:
        time.sleep(1.0)

    if captcha_visible(page):
        return LoginResult(False, captcha=True, message="캡차 표시됨")

    if "nid.naver.com" not in page.url:
        return LoginResult(True, message="로그인 성공")

    if login_error_visible(page):
        return LoginResult(False, message="아이디·비밀번호 오류 또는 추가 인증 필요")

    return LoginResult(False, message="로그인 페이지에 남아 있음")


def wait_for_manual_login(page: Page, *, prompt: str = "") -> None:
    if prompt:
        print(prompt)
    print("캡차·OTP가 보이면 브라우저에서 처리한 뒤, 로그인 완료 시 Enter…")
    input()


def ensure_naver_login(
    page: Page,
    naver_id: str,
    password: str,
    *,
    allow_manual: bool = True,
    fast: bool | None = None,
) -> LoginResult:
    """로그인 시도 → 캡차 시 수동 대기(선택)."""
    result = human_login(page, naver_id, password, fast=fast)
    if result.ok:
        return result

    if result.captcha and allow_manual:
        wait_for_manual_login(page, prompt="영수증 캡차 등 자동입력 방지가 표시되었습니다.")
        _pause(300, 500)
        if "nid.naver.com" not in page.url:
            return LoginResult(True, message="수동 인증 후 로그인 성공")
        return LoginResult(False, captcha=True, message="캡차 처리 후에도 로그인 실패")

    if allow_manual and "nid.naver.com" in page.url:
        wait_for_manual_login(page, prompt="자동 로그인이 완료되지 않았습니다. 브라우저에서 로그인해 주세요.")
        if "nid.naver.com" not in page.url:
            return LoginResult(True, message="수동 로그인 성공")

    return result
