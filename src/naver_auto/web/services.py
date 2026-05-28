"""웹 UI용 서비스 — CLI 로직 재사용."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from naver_auto.content.gemini_client import gemini_configured
from naver_auto.content.generator import create_draft_from_keyword
from naver_auto.image.resolver import resolve_draft_images
from naver_auto.paths import DRAFTS_DIR, ensure_dirs, naver_api_configured
from naver_auto.publish.daily_limit import can_publish, count_today, daily_limit
from naver_auto.publish.playwright_client import session_exists
from naver_auto.publish.uploader import publish_draft
from naver_auto.web.jobs import Job


def find_draft_dir(draft_id: str) -> Path:
    direct = DRAFTS_DIR / draft_id
    if direct.exists():
        return direct
    matches = list(DRAFTS_DIR.glob(f"*{draft_id}*"))
    if not matches:
        raise FileNotFoundError(f"초안 없음: {draft_id}")
    return matches[0]


def load_meta(draft_dir: Path) -> dict[str, Any]:
    return json.loads((draft_dir / "meta.json").read_text(encoding="utf-8"))


def pipeline_status() -> dict[str, Any]:
    ensure_dirs()
    counts = {"total": 0, "draft_ready": 0, "review": 0, "naver_draft": 0, "published": 0}
    for path in DRAFTS_DIR.iterdir():
        if not path.is_dir() or not (path / "meta.json").exists():
            continue
        meta = load_meta(path)
        counts["total"] += 1
        st = meta.get("status", "")
        if st in counts:
            counts[st] += 1
        elif st == "ready_to_publish":
            counts["draft_ready"] += 1
    ok, limit_msg = can_publish()
    return {
        "drafts": counts,
        "published_today": count_today(),
        "daily_limit": daily_limit(),
        "can_publish": ok,
        "limit_message": limit_msg if not ok else "",
        "session_ok": session_exists(),
        "gemini_ok": gemini_configured(),
        "naver_api_ok": naver_api_configured(),
        "drafts_dir": str(DRAFTS_DIR),
    }


def list_drafts(*, status: str | None = None) -> list[dict[str, Any]]:
    ensure_dirs()
    rows: list[dict[str, Any]] = []
    for path in sorted(DRAFTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_dir() or not (path / "meta.json").exists():
            continue
        meta = load_meta(path)
        st = meta.get("status", "?")
        if status and st != status:
            continue
        images_dir = path / "images"
        img_count = len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0
        rows.append(
            {
                "draft_id": meta.get("draft_id", path.name),
                "keyword": meta.get("keyword", ""),
                "title": meta.get("title", ""),
                "status": st,
                "char_count": meta.get("char_count", 0),
                "image_count": img_count,
                "generated_at": meta.get("generated_at"),
                "published_at": meta.get("published_at"),
                "naver_url": meta.get("naver_url"),
            }
        )
    return rows


def draft_detail(draft_id: str) -> dict[str, Any]:
    draft_dir = find_draft_dir(draft_id)
    meta = load_meta(draft_dir)
    body = (draft_dir / "body.md").read_text(encoding="utf-8")
    images: list[dict[str, str]] = []
    images_dir = draft_dir / "images"
    if images_dir.exists():
        for p in sorted(images_dir.glob("*.jpg")):
            images.append({"name": p.name, "slot": p.stem})
    return {
        "draft_id": meta.get("draft_id", draft_dir.name),
        "meta": meta,
        "body": body,
        "images": images,
        "image_plan": meta.get("image_plan", []),
    }


def run_create(job: Job, *, keyword: str, category: str | None, skip_polish: bool) -> dict[str, Any]:
    job.message = f"초안 생성 중: {keyword}"
    job.logs.append(f"[create] 키워드: {keyword}")
    out_dir = create_draft_from_keyword(keyword, category=category, skip_polish=skip_polish)
    job.logs.append(f"본문 저장: {out_dir.name}")
    job.logs.append("이미지 수집 중…")
    resolve_draft_images(out_dir)
    meta = load_meta(out_dir)
    job.logs.append(f"완료 — {meta.get('char_count', 0)}자, 이미지 {meta.get('image_count', 0)}장")
    return {"draft_id": meta.get("draft_id", out_dir.name), "status": meta.get("status")}


def run_fetch_images(job: Job, draft_id: str, *, force: bool) -> dict[str, Any]:
    draft_dir = find_draft_dir(draft_id)
    job.message = f"이미지 {'재' if force else ''}수집 중"
    job.logs.append(f"[fetch-images] {draft_dir.name}")
    paths = resolve_draft_images(draft_dir, force=force)
    meta = load_meta(draft_dir)
    sources = meta.get("image_sources", [])
    job.logs.append(f"→ {len(paths)}장 ({', '.join(sources[:6])})")
    return {"draft_id": draft_id, "image_count": len(paths), "sources": sources}


def run_publish(job: Job, draft_id: str, *, live: bool, refresh_images: bool) -> dict[str, Any]:
    ok, msg = can_publish()
    if not ok:
        raise RuntimeError(msg)
    draft_dir = find_draft_dir(draft_id)
    if refresh_images:
        job.logs.append("이미지 재수집…")
        resolve_draft_images(draft_dir, force=True)
    job.message = "네이버 업로드 중 (브라우저가 열립니다)"
    job.logs.append(f"[publish] {draft_id} ({'live' if live else 'draft'})")
    job.logs.append("Playwright 실행 — Chrome 창을 닫지 마세요")

    def _log(step: str) -> None:
        job.logs.append(step)

    out = publish_draft(
        draft_id,
        live=live,
        allow_manual_login=False,
        log=_log,
    )
    meta = load_meta(out)
    job.logs.append(f"→ status={meta.get('status')}")
    if meta.get("naver_url"):
        job.logs.append(f"url={meta['naver_url']}")
    return {
        "draft_id": draft_id,
        "status": meta.get("status"),
        "naver_url": meta.get("naver_url"),
    }
