"""초안 이미지 해석 및 생성 — 슬롯별 AI 계획 + 검색."""

from __future__ import annotations

import hashlib
import json
import time
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
    refetch: bool = False,
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
                references=refs if slot == 1 and not refetch else None,
                refetch=refetch,
                slot=slot,
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


def _slot_count(body: str, images_dir: Path) -> int:
    slot_nums = _extract_image_slots(body)
    from_disk = 0
    if images_dir.exists():
        stems = [int(p.stem) for p in images_dir.glob("*.jpg") if p.stem.isdigit()]
        from_disk = max(stems) if stems else 0
    return max(len(slot_nums), max(slot_nums) if slot_nums else 0, from_disk, 6)


def _url_hash(url: str) -> str:
    return hashlib.md5(url.split("?")[0].encode()).hexdigest()[:12]


def _draft_used_hashes(meta: dict) -> set[str]:
    """이 초안에서 이미 쓴 이미지 URL — 재수집 시 동일 URL 재선택 방지."""
    used: set[str] = set()
    for raw in meta.get("used_image_hashes") or []:
        if raw:
            used.add(str(raw)[:32])
    for attr in meta.get("image_attributions") or []:
        if not isinstance(attr, dict):
            continue
        for key in ("image_url", "page_url"):
            url = str(attr.get(key, "")).strip()
            if url:
                used.add(_url_hash(url))
    return used


def _ban_hashes_from_attributions(attributions: list[dict]) -> set[str]:
    banned: set[str] = set()
    for attr in attributions:
        if not isinstance(attr, dict):
            continue
        for key in ("image_url", "page_url"):
            url = str(attr.get(key, "")).strip()
            if url:
                banned.add(_url_hash(url))
    return banned


def _bump_plan_for_refetch(
    plan: dict[int, dict],
    refetch_slots: set[int],
    *,
    keyword: str,
    attempt: int,
) -> None:
    suffixes = (" 레시피", " 만드는법", " 음식 사진", " 집에서", " 요리")
    for slot in sorted(refetch_slots):
        item = plan.get(slot)
        if not item:
            continue
        base = str(item.get("search_query") or item.get("section") or keyword).strip()
        suffix = suffixes[(slot + attempt) % len(suffixes)]
        item["search_query"] = f"{base}{suffix}"[:55]


def _merge_attributions(
    prev: list[dict],
    new_attrs: list[dict],
    *,
    slot_count: int,
) -> list[dict]:
    by_slot: dict[int, dict] = {}
    for item in prev:
        if isinstance(item, dict) and item.get("slot") is not None:
            by_slot[int(item["slot"])] = item
    for item in new_attrs:
        if isinstance(item, dict) and item.get("slot") is not None:
            by_slot[int(item["slot"])] = item
    return [by_slot[i] for i in range(1, slot_count + 1) if i in by_slot]


def resolve_draft_images(
    draft_dir: Path,
    *,
    force: bool = False,
    keep_slots: set[int] | None = None,
) -> list[Path]:
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

    slot_count = _slot_count(body, images_dir)
    all_slots = set(range(1, slot_count + 1))

    if keep_slots is not None:
        keep = {int(s) for s in keep_slots if int(s) in all_slots}
        refetch_slots = all_slots - keep
        full_refresh = force and not keep
    elif force:
        keep = set()
        refetch_slots = all_slots
        full_refresh = True
    else:
        keep = {
            i
            for i in all_slots
            if (images_dir / f"{i:02d}.jpg").exists()
            and (images_dir / f"{i:02d}.jpg").stat().st_size > 0
        }
        refetch_slots = all_slots - keep
        full_refresh = False

    if not refetch_slots:
        return sorted(images_dir.glob("*.jpg"))[:slot_count]

    if full_refresh:
        for old in images_dir.glob("*.jpg"):
            old.unlink()
        if planning_cfg.get("enabled", True):
            ensure_image_plan(draft_dir, regen=True)
    else:
        for slot in refetch_slots:
            path = images_dir / f"{slot:02d}.jpg"
            if path.exists():
                path.unlink()
        if planning_cfg.get("enabled", True):
            ensure_image_plan(draft_dir, regen=False)

    plan = plan_by_slot(meta.get("image_plan") or ensure_image_plan(draft_dir))

    inbox_dir = INBOX_DIR / keyword
    user_files = sorted(
        [p for p in inbox_dir.glob("*") if p.is_file()] if inbox_dir.exists() else []
    )
    refs = meta.get("references", [])
    prev_attributions = list(meta.get("image_attributions") or [])
    used_hashes = _draft_used_hashes(meta)
    if refetch_slots:
        used_hashes |= _ban_hashes_from_attributions(
            [a for a in prev_attributions if int(a.get("slot", -1)) in refetch_slots]
        )
        attempt = int(meta.get("image_refetch_count", 0)) + 1
        meta["image_refetch_count"] = attempt
        _bump_plan_for_refetch(plan, refetch_slots, keyword=keyword, attempt=attempt)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    new_attributions: list[dict] = []
    gemini_used = 0

    created: list[Path] = []
    for i in range(1, slot_count + 1):
        out_path = images_dir / f"{i:02d}.jpg"
        if i not in refetch_slots and out_path.exists() and out_path.stat().st_size > 0:
            created.append(out_path)
            continue

        slot_plan = plan.get(i)
        is_refetch = i in refetch_slots
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
            refetch=is_refetch,
        )
        if ok:
            created.append(out_path)
            if attr:
                attr["slot"] = i
                new_attributions.append(attr)

    created = sorted(images_dir.glob("*.jpg"))[:slot_count]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    merged = _merge_attributions(prev_attributions, new_attributions, slot_count=slot_count)
    meta["images_resolved"] = True
    meta["image_count"] = len(created)
    meta["images_version"] = int(time.time())
    by_slot = {int(a["slot"]): a for a in merged if a.get("slot") is not None}
    meta["image_sources"] = [
        str(by_slot.get(int(p.stem), {}).get("source", "")) for p in created
    ]
    meta["image_attributions"] = merged[:20]
    meta["image_refetch_slots"] = sorted(refetch_slots)
    all_hashes = _draft_used_hashes(meta)
    for attr in merged:
        if isinstance(attr, dict):
            for key in ("image_url", "page_url"):
                url = str(attr.get(key, "")).strip()
                if url:
                    all_hashes.add(_url_hash(url))
    meta["used_image_hashes"] = sorted(all_hashes)[:200]
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return created
