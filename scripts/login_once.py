#!/usr/bin/env python3
"""네이버 로그인 후 storage_state 저장 및 (선택) 임시저장.

기본: .env 계정으로 **한 글자씩 천천히** 자동 로그인.
캡차·OTP만 나올 때 브라우저에서 처리 후 Enter.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 시스템 python으로 실행 시 프로젝트 .venv 사용
_VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.is_file() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    raise SystemExit(
        subprocess.call([str(_VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])
    )

sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from naver_auto.paths import DRAFTS_DIR, ensure_dirs  # noqa: E402
from naver_auto.publish.daily_limit import can_publish, record_publish  # noqa: E402
from naver_auto.publish.naver_login import (  # noqa: E402
    LOGIN_URL,
    ensure_naver_login,
)
from naver_auto.publish.editor_context import find_editor_root  # noqa: E402
from naver_auto.publish.editor_actions import dismiss_popups  # noqa: E402
from naver_auto.publish.playwright_client import (  # noqa: E402
    browser_context,
    editor_ready,
    goto_write_page,
    save_storage_state,
    wait_for_editor,
    write_url,
)
from naver_auto.publish.uploader import upload_draft_on_page  # noqa: E402


def _find_draft(draft_id: str) -> Path:
    direct = DRAFTS_DIR / draft_id
    if direct.exists():
        return direct
    matches = list(DRAFTS_DIR.glob(f"*{draft_id}*"))
    if not matches:
        raise SystemExit(f"초안 없음: {draft_id}")
    return matches[0]


def _open_editor_or_login(page, naver_id: str, password: str, *, manual_only: bool):
    try:
        goto_write_page(page, log=print)
    except RuntimeError:
        pass
    for _ in range(8):
        root = find_editor_root(page)
        if root:
            dismiss_popups(page, root=root)
            print(f"이미 로그인됨 — {write_url()}")
            return root
        time.sleep(0.4)

    page.goto(LOGIN_URL, wait_until="domcontentloaded")

    if manual_only:
        print(f"수동 로그인 모드 — 계정: {naver_id or '(미설정)'}")
        print("브라우저에서 로그인 후 Enter…")
        input()
    else:
        print(f"자동 로그인 시도 ({naver_id}) — 한 글자씩 입력 중…", flush=True)
        result = ensure_naver_login(page, naver_id, password, allow_manual=True)
        if not result.ok:
            print(f"로그인 실패: {result.message}")
            return None
        print(result.message)

    goto_write_page(page, log=print)
    root = find_editor_root(page)
    if root:
        dismiss_popups(page, root=root)
        print(f"글쓰기 에디터 확인: {write_url()}")
        return root
    root = wait_for_editor(page, timeout_ms=30000)
    dismiss_popups(page, root=root)
    print(f"글쓰기 에디터 확인: {write_url()}")
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 블로그 로그인·임시저장")
    parser.add_argument(
        "--manual",
        action="store_true",
        help="자동 입력 없이 브라우저에서 직접 로그인",
    )
    parser.add_argument(
        "--paste",
        action="store_true",
        help="(비추천) 클립보드 붙여넣기 로그인",
    )
    parser.add_argument(
        "--publish",
        metavar="DRAFT_ID",
        help="로그인 후 같은 브라우저에서 바로 임시저장",
    )
    parser.add_argument("--live", action="store_true", help="임시저장 대신 즉시 발행")
    parser.add_argument(
        "--refresh-images",
        action="store_true",
        help="이미지 계획 재생성 + 슬롯별 이미지 재수집",
    )
    args = parser.parse_args()
    ensure_dirs()

    naver_id = os.getenv("NAVER_ID", "").strip()
    password = os.getenv("NAVER_PASSWORD", "").strip()

    if args.paste:
        import pyperclip

        def _paste_login(page):
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.locator("#id").first.click()
            pyperclip.copy(naver_id)
            page.keyboard.press("Meta+V")
            page.locator("#pw").first.click()
            pyperclip.copy(password)
            page.keyboard.press("Meta+V")
            page.locator("#log\\.login").first.click()
            time.sleep(3)

    with browser_context(headless=False) as (_, context):
        page = context.new_page()

        editor_root = None
        if args.paste and naver_id and password:
            _paste_login(page)
            page.goto(write_url(), wait_until="domcontentloaded")
            editor_root = wait_for_editor(page)
        else:
            editor_root = _open_editor_or_login(
                page, naver_id, password, manual_only=args.manual
            )
            if not editor_root:
                return 1

        if not editor_ready(page):
            print(f"에디터 없음 — URL: {page.url}")
            return 1

        path = save_storage_state(context)
        print(f"세션 저장: {path}")

        if args.publish:
            ok, msg = can_publish()
            if not ok:
                print(msg)
                return 1
            draft_dir = _find_draft(args.publish)
            from naver_auto.image.resolver import resolve_draft_images

            print(f"임시저장: {draft_dir.name} …", flush=True)
            print("이미지 확인…", flush=True)
            resolve_draft_images(draft_dir, force=args.refresh_images)
            print("에디터에 글 붙이는 중…", flush=True)
            url = upload_draft_on_page(
                page, draft_dir, live=args.live, root=editor_root
            )
            meta_path = draft_dir / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "published" if args.live else "naver_draft"
            meta["naver_url"] = url
            meta["published_at"] = datetime.now(timezone.utc).isoformat()
            with meta_path.open("w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            record_publish(
                meta.get("draft_id", draft_dir.name),
                mode="live" if args.live else "draft",
                url=url,
            )
            print(f"완료: status={meta['status']}")
            if url:
                print(f"url={url}")
        else:
            print("다음: python scripts/login_once.py --publish draft_탕수육_97a6910e04")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
