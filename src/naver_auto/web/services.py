"""웹 UI용 서비스 — CLI 로직 재사용."""

from __future__ import annotations

import json
import os
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
    img_version = int(meta.get("images_version") or 0)
    if images_dir.exists():
        for p in sorted(images_dir.glob("*.jpg")):
            images.append(
                {
                    "name": p.name,
                    "slot": p.stem,
                    "mtime": int(p.stat().st_mtime),
                }
            )
    return {
        "draft_id": meta.get("draft_id", draft_dir.name),
        "meta": meta,
        "body": body,
        "images": images,
        "image_plan": meta.get("image_plan", []),
        "images_version": img_version,
    }


def run_create(
    job: Job,
    *,
    keyword: str,
    category: str | None,
    slot_prompts: dict[int, str] | None = None,
) -> dict[str, Any]:
    job.message = f"초안 생성 중: {keyword}"
    job.logs.append(f"[create] 키워드: {keyword}")
    if slot_prompts:
        for slot, prompt in sorted(slot_prompts.items()):
            if str(prompt).strip():
                job.logs.append(f"#{slot} 이미지: {str(prompt).strip()[:60]}")

    def on_progress(msg: str) -> None:
        job.message = msg
        job.logs.append(msg)

    out_dir = create_draft_from_keyword(
        keyword,
        category=category,
        slot_prompts=slot_prompts,
        progress=on_progress,
    )
    meta = load_meta(out_dir)
    job.logs.append(f"본문 저장: {out_dir.name} — {meta.get('char_count', 0)}자")

    fetch_on_create = os.getenv("NAVER_CREATE_FETCH_IMAGES", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if fetch_on_create:
        on_progress("이미지 생성 중… (FLUX.1-schnell)")
        job.logs.append("NVIDIA FLUX.1-schnell 이미지 생성 시작")
        paths = resolve_draft_images(out_dir, progress=on_progress)
        meta = load_meta(out_dir)
        job.logs.append(f"이미지 {len(paths)}장 — {', '.join(meta.get('image_sources', [])[:6])}")
        for err in meta.get("image_generation_errors") or []:
            job.logs.append(f"FLUX 오류: {err}")

    job.message = "초안 생성 완료"
    return {"draft_id": meta.get("draft_id", out_dir.name), "status": meta.get("status")}


def run_fetch_images(
    job: Job,
    draft_id: str,
    *,
    force: bool,
    keep_slots: list[int] | None = None,
    slot_prompts: dict[str, str] | None = None,
) -> dict[str, Any]:
    draft_dir = find_draft_dir(draft_id)
    keep = {int(s) for s in keep_slots} if keep_slots is not None else None
    job.message = "FLUX 이미지 생성 중"
    job.logs.append(f"[fetch-images] {draft_dir.name} (FLUX.1-schnell)")
    if keep is not None:
        job.logs.append(f"유지 슬롯: {sorted(keep)}")
    if slot_prompts:
        for slot, prompt in sorted(slot_prompts.items(), key=lambda x: int(x[0])):
            if str(prompt).strip():
                job.logs.append(f"#{slot} 프롬프트: {str(prompt).strip()[:80]}")
    parsed_slot_prompts = (
        {int(k): str(v) for k, v in slot_prompts.items() if str(v).strip()}
        if slot_prompts
        else None
    )
    paths = resolve_draft_images(
        draft_dir,
        force=force,
        keep_slots=keep,
        slot_prompts=parsed_slot_prompts,
        progress=lambda msg: (job.logs.append(msg), setattr(job, "message", msg)),
    )
    meta = load_meta(draft_dir)
    refetched = meta.get("image_refetch_slots", [])
    sources = meta.get("image_sources", [])
    job.logs.append(
        f"재수집: {refetched or '전체'} → {len(paths)}장 ({', '.join(sources[:6])})"
    )
    return {
        "draft_id": draft_id,
        "image_count": len(paths),
        "sources": sources,
        "refetched_slots": refetched,
    }


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
