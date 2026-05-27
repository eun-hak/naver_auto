"""초안 이미지 해석 및 생성."""

from __future__ import annotations

import json
from pathlib import Path

from naver_auto.image.cards import create_card_image, create_placeholder_set
from naver_auto.image.gemini import gemini_configured, generate_or_fallback
from naver_auto.image.sns_fetcher import fetch_images_for_slots
from naver_auto.paths import INBOX_DIR, load_yaml


def _extract_image_slots(body: str) -> list[tuple[int, str]]:
    import re

    pattern = re.compile(r"!\[이미지\s*(\d+)\]\(images/(\d+)\.jpg\)")
    slots: list[tuple[int, str]] = []
    for match in pattern.finditer(body):
        slots.append((int(match.group(1)), match.group(2)))
    return slots


def resolve_draft_images(draft_dir: Path, *, force: bool = False) -> list[Path]:
    meta_path = draft_dir / "meta.json"
    body_path = draft_dir / "body.md"
    if not meta_path.exists() or not body_path.exists():
        raise FileNotFoundError(f"초안 없음: {draft_dir}")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    body = body_path.read_text(encoding="utf-8")
    publish_cfg = load_yaml("publish.yaml")
    priority = publish_cfg.get("image_priority", ["user", "sns", "news_og", "gemini", "card"])
    gemini_limit = int(publish_cfg.get("gemini_images_per_post", 2))
    sns_cfg = publish_cfg.get("sns", {})

    keyword = meta.get("keyword", "블로그")
    images_dir = draft_dir / "images"
    images_dir.mkdir(exist_ok=True)

    slots = _extract_image_slots(body)
    slot_count = max(len(slots), 6)

    if force:
        for old in images_dir.glob("*.jpg"):
            old.unlink()

    inbox_dir = INBOX_DIR / keyword
    user_files = sorted(
        [p for p in inbox_dir.glob("*") if p.is_file()] if inbox_dir.exists() else []
    )
    refs = meta.get("references", [])
    attributions: list[dict[str, str]] = list(meta.get("image_attributions", []))

    created: list[Path] = []
    gemini_used = 0
    sns_used = False

    for i in range(1, slot_count + 1):
        out_path = images_dir / f"{i:02d}.jpg"
        if not force and out_path.exists() and out_path.stat().st_size > 0:
            created.append(out_path)
            continue

        resolved = False
        for source in priority:
            if source == "user" and user_files:
                src = user_files[(i - 1) % len(user_files)]
                out_path.write_bytes(src.read_bytes())
                created.append(out_path)
                attributions.append({"source": "user", "page_url": str(src)})
                resolved = True
                break

            if source == "sns" and sns_cfg.get("enabled", True) and not sns_used:
                saved, attrs = fetch_images_for_slots(
                    keyword,
                    slot_count=slot_count,
                    references=refs,
                    cfg=sns_cfg,
                    images_dir=images_dir,
                )
                if saved:
                    sns_used = True
                    attributions.extend(attrs)
                    created = saved[:slot_count]
                    while len(created) < slot_count:
                        idx = len(created) + 1
                        fallback = images_dir / f"{idx:02d}.jpg"
                        create_card_image(
                            fallback,
                            title=keyword,
                            subtitle=f"섹션 {idx}",
                            index=idx - 1,
                        )
                        created.append(fallback)
                    resolved = True
                    break

            if source == "gemini" and gemini_configured() and gemini_used < gemini_limit:
                generate_or_fallback(
                    out_path,
                    keyword=keyword,
                    section_hint=f"섹션 {i}",
                    index=i - 1,
                )
                created.append(out_path)
                attributions.append({"source": "gemini", "page_url": ""})
                gemini_used += 1
                resolved = True
                break

            if source == "card":
                create_card_image(
                    out_path,
                    title=keyword,
                    subtitle=f"섹션 {i}",
                    index=i - 1,
                )
                created.append(out_path)
                attributions.append({"source": "card", "page_url": ""})
                resolved = True
                break

        if resolved and sns_used:
            break

        if not resolved:
            create_card_image(
                out_path,
                title=keyword,
                subtitle=f"섹션 {i}",
                index=i - 1,
            )
            created.append(out_path)

    created = sorted(images_dir.glob("*.jpg"))[:slot_count]
    meta["images_resolved"] = True
    meta["image_count"] = len(created)
    meta["image_sources"] = [a.get("source", "") for a in attributions[: len(created)]]
    meta["image_attributions"] = attributions[:20]
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return created
