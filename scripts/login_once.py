#!/usr/bin/env python3
"""네이버 로그인 후 storage_state 저장."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from naver_auto.publish.playwright_client import (  # noqa: E402
    browser_context,
    save_storage_state,
)


def _auto_login(page, naver_id: str, password: str) -> None:
    import pyperclip

    page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
    time.sleep(1)

    id_input = page.locator("#id").first
    pw_input = page.locator("#pw").first
    id_input.click()
    pyperclip.copy(naver_id)
    page.keyboard.press("Meta+V") if sys.platform == "darwin" else page.keyboard.press("Control+V")
    time.sleep(0.3)
    pw_input.click()
    pyperclip.copy(password)
    page.keyboard.press("Meta+V") if sys.platform == "darwin" else page.keyboard.press("Control+V")
    time.sleep(0.3)
    page.locator("#log\\.login, button.btn_login").first.click()
    time.sleep(3)


def main() -> int:
    naver_id = os.getenv("NAVER_ID", "").strip()
    password = os.getenv("NAVER_PASSWORD", "").strip()

    with browser_context(headless=False) as (_, context):
        page = context.new_page()
        if naver_id and password:
            print(f"NAVER_ID({naver_id})로 자동 로그인 시도…")
            _auto_login(page, naver_id, password)
            if "nid.naver.com" in page.url:
                print("추가 인증(OTP/캡차)이 필요할 수 있습니다. 브라우저에서 완료 후 Enter…")
                input()
        else:
            page.goto("https://nid.naver.com/nidlogin.login", wait_until="domcontentloaded")
            print("브라우저에서 수동 로그인 후 Enter…")
            input()

        page.goto("https://blog.naver.com", wait_until="domcontentloaded")
        time.sleep(2)
        path = save_storage_state(context)
        print(f"세션 저장: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
