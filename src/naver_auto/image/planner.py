"""body.md 슬롯별 AI 이미지 계획."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from naver_auto.content.gemini_client import gemini_configured, plan_image_slots
from naver_auto.paths import load_yaml

IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\(images/(\d+)\.jpg\)")


def extract_slot_contexts(body: str) -> list[dict[str, Any]]:
    """각 이미지 슬롯 → 바로 위 ## 소제목(### 보다 ## 우선) 매핑."""
    lines = body.splitlines()
    current_h2 = ""
    current_h3 = ""
    slots: list[dict[str, Any]] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("### "):
            current_h2 = stripped[3:].strip()
            current_h3 = ""
        elif stripped.startswith("### "):
            current_h3 = stripped[4:].strip()
        match = IMAGE_MD_RE.search(line)
        if not match:
            continue
        slot = int(match.group(2))
        alt = match.group(1).strip()
        section = current_h2 or current_h3 or f"섹션 {slot}"
        slots.append(
            {
                "slot": slot,
                "section": section,
                "alt": alt if alt and not alt.startswith("이미지") else "",
            }
        )

    slots.sort(key=lambda s: s["slot"])
    return slots


def _fallback_plan(keyword: str, slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for item in slots:
        section = item.get("section") or keyword
        query = section if section != keyword else f"{keyword} 맛집"
        plan.append(
            {
                "slot": item["slot"],
                "section": section,
                "search_query": query[:40],
                "alt": item.get("alt") or section,
                "gemini_prompt": f"{section}, food photography, no text",
            }
        )
    return plan


def build_image_plan(
    *,
    keyword: str,
    title: str,
    body: str,
    slots: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not slots:
        slots = extract_slot_contexts(body)
    if not slots:
        return []

    cfg = load_yaml("publish.yaml").get("image_planning", {})
    if cfg.get("enabled", True) and gemini_configured():
        try:
            return plan_image_slots(
                keyword=keyword,
                title=title,
                slots=slots,
                body_excerpt=body[:2500],
            )
        except Exception:
            pass
    return _fallback_plan(keyword, slots)


def ensure_image_plan(
    draft_dir: Path,
    *,
    regen: bool = False,
) -> list[dict[str, Any]]:
    meta_path = draft_dir / "meta.json"
    body_path = draft_dir / "body.md"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body = body_path.read_text(encoding="utf-8")

    if meta.get("image_plan") and not regen:
        return meta["image_plan"]

    slots = extract_slot_contexts(body)
    plan = build_image_plan(
        keyword=meta.get("keyword", "블로그"),
        title=meta.get("title") or meta.get("seo_title", ""),
        body=body,
        slots=slots,
    )
    meta["image_plan"] = plan
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return plan


def plan_by_slot(plan: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(item["slot"]): item for item in plan if "slot" in item}
