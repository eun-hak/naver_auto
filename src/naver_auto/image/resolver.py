"""초안 이미지 해석 및 생성 — 슬롯별 AI 계획 + 검색."""

from __future__ import annotations

import json
from pathlib import Path

from naver_auto.image.cards import create_card_image
from naver_auto.image.gemini import gemini_configured, generate_gemini_image
from naver_auto.image.planner import ensure_image_plan, plan_by_slot
from naver_auto.image.sns_fetcher import fetch_one_image
from naver_auto.paths import INBOX_DIR, load_yaml


def _extract_image_slots(body: str) -> list[int]:
    import re

    pattern = re.compile(r"!\[이미지\s*(\d+)\]\(images/(\d+)\.jpg\)")
    nums: list[int] = []
    for match in pattern.finditer(body):
        nums.append(int(match.group(2)))
    return nums


def _resolve_slot_image(
    slot: int,
    *,
    out_path: Path,
    keyword: str,
    slot_plan: dict | None,
    publish_cfg: dict,
    sns_cfg: dict,
    refs: list,
    user_files: list[Path],
    used_hashes: set[str],
    gemini_used: int,
    gemini_limit: int,
) -> tuple[bool, dict, int]:
    priority = publish_cfg.get("image_priority", ["user", "sns", "gemini", "card"])
    section = (slot_plan or {}).get("section") or f"섹션 {slot}"
    search_query = (slot_plan or {}).get("search_query") or section or keyword
    gemini_prompt = (slot_plan or {}).get("gemini_prompt") or f"{section} food photo, no text"
    subtitle = section[:40]

    for source in priority:
        if source == "user" and user_files:
            src = user_files[(slot - 1) % len(user_files)]
            out_path.write_bytes(src.read_bytes())
            return True, {"source": "user", "page_url": str(src), "search_query": search_query}, gemini_used

        if source == "sns" and sns_cfg.get("enabled", True):
            ok, attr = fetch_one_image(
                search_query,
                out_path,
                cfg=sns_cfg,
                used_url_hashes=used_hashes,
                references=refs if slot == 1 else None,
            )
            if ok and attr:
                attr["source"] = attr.get("source") or "sns"
                attr["slot"] = slot
                return True, attr, gemini_used

        if source == "gemini" and gemini_configured() and gemini_used < gemini_limit:
            result = generate_gemini_image(
                out_path,
                prompt=gemini_prompt,
                keyword=keyword,
                index=slot - 1,
            )
            if result:
                return (
                    True,
                    {
                        "source": "gemini",
                        "page_url": "",
                        "search_query": search_query,
                        "slot": slot,
                    },
                    gemini_used + 1,
                )

        if source == "card":
            create_card_image(out_path, title=keyword, subtitle=subtitle, index=slot - 1)
            return (
                True,
                {"source": "card", "page_url": "", "search_query": search_query, "slot": slot},
                gemini_used,
            )

    create_card_image(out_path, title=keyword, subtitle=subtitle, index=slot - 1)
    return (
        True,
        {"source": "card", "page_url": "", "search_query": search_query, "slot": slot},
        gemini_used,
    )


def resolve_draft_images(draft_dir: Path, *, force: bool = False) -> list[Path]:
    meta_path = draft_dir / "meta.json"
    body_path = draft_dir / "body.md"
    if not meta_path.exists() or not body_path.exists():
        raise FileNotFoundError(f"초안 없음: {draft_dir}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body = body_path.read_text(encoding="utf-8")
    publish_cfg = load_yaml("publish.yaml")
    sns_cfg = publish_cfg.get("sns", {})
    gemini_limit = int(publish_cfg.get("gemini_images_per_post", 2))
    planning_cfg = publish_cfg.get("image_planning", {})

    keyword = meta.get("keyword", "블로그")
    images_dir = draft_dir / "images"
    images_dir.mkdir(exist_ok=True)

    slot_nums = _extract_image_slots(body)
    slot_count = max(len(slot_nums), max(slot_nums) if slot_nums else 0, 6)

    if force:
        for old in images_dir.glob("*.jpg"):
            old.unlink()
        if planning_cfg.get("enabled", True):
            ensure_image_plan(draft_dir, regen=True)
    elif planning_cfg.get("enabled", True):
        ensure_image_plan(draft_dir, regen=False)

    plan = plan_by_slot(meta.get("image_plan") or ensure_image_plan(draft_dir))

    inbox_dir = INBOX_DIR / keyword
    user_files = sorted(
        [p for p in inbox_dir.glob("*") if p.is_file()] if inbox_dir.exists() else []
    )
    refs = meta.get("references", [])
    attributions: list[dict] = []
    used_hashes: set[str] = set()
    gemini_used = 0

    created: list[Path] = []
    for i in range(1, slot_count + 1):
        out_path = images_dir / f"{i:02d}.jpg"
        if not force and out_path.exists() and out_path.stat().st_size > 0:
            created.append(out_path)
            continue

        slot_plan = plan.get(i)
        ok, attr, gemini_used = _resolve_slot_image(
            i,
            out_path=out_path,
            keyword=keyword,
            slot_plan=slot_plan,
            publish_cfg=publish_cfg,
            sns_cfg=sns_cfg,
            refs=refs,
            user_files=user_files,
            used_hashes=used_hashes,
            gemini_used=gemini_used,
            gemini_limit=gemini_limit,
        )
        if ok:
            created.append(out_path)
            attributions.append(attr)

    created = sorted(images_dir.glob("*.jpg"))[:slot_count]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["images_resolved"] = True
    meta["image_count"] = len(created)
    meta["image_sources"] = [a.get("source", "") for a in attributions[: len(created)]]
    meta["image_attributions"] = attributions[:20]
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return created
