"""키워드 → 블로그 초안 생성."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from naver_auto.content.gemini_client import (
    gemini_configured,
    generate_blog_body as gemini_body,
    generate_meta_tags as gemini_meta,
    generate_title_candidates as gemini_titles,
    polish_intro as gemini_polish,
)
from naver_auto.content.groq_client import (
    generate_blog_body as groq_body,
    generate_meta_tags as groq_meta,
    generate_title_candidates as groq_titles,
    polish_intro as groq_polish,
)
from naver_auto.content.validator import (
    extract_title,
    insert_image_placeholders,
    normalize_draft_body,
    quality_check,
)
from naver_auto.keyword.analyzer import analyze_keyword
from naver_auto.keyword.references import (
    fetch_blog_references,
    reference_titles,
    summarize_references,
)
from naver_auto.paths import DRAFTS_DIR, ensure_dirs, load_yaml


def _draft_id(keyword: str) -> str:
    digest = hashlib.sha1(keyword.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^\w가-힣]+", "-", keyword.strip())[:24].strip("-")
    return f"draft_{slug}_{digest}" if slug else f"draft_{digest}"


def create_draft_from_keyword(
    keyword: str,
    *,
    category: str | None = None,
    skip_polish: bool = False,
) -> Path:
    ensure_dirs()
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("키워드가 비어 있습니다.")

    if not gemini_configured():
        from naver_auto.content.groq_client import get_api_key

        get_api_key()

    seo_cfg = load_yaml("seo_style.yaml")
    publish_cfg = load_yaml("publish.yaml")
    category = category or publish_cfg.get("default_category", "일반")

    research = analyze_keyword(keyword)
    gemini_research = research.get("gemini_research", {})
    refs = fetch_blog_references(keyword)
    ref_summary = summarize_references(refs)
    ref_titles = reference_titles(refs)

    use_gemini = gemini_configured()
    if use_gemini:
        titles = gemini_titles(
            keyword,
            related_keywords=research.get("related_keywords", []),
            reference_titles=ref_titles,
            research=gemini_research,
        )
    else:
        titles = groq_titles(
            keyword,
            related_keywords=research.get("related_keywords", []),
            reference_titles=ref_titles,
        )
    seo_title = titles[0]

    min_c = seo_cfg.get("body", {}).get("min_chars", 1500)
    max_c = seo_cfg.get("body", {}).get("max_chars", 3500)
    img_count = seo_cfg.get("image_placeholder_count", 6)

    body = ""
    errors: list[str] = []
    for attempt in range(2):
        if use_gemini:
            body = gemini_body(
                seo_title,
                keyword,
                min_chars=min_c,
                max_chars=max_c,
                reference_summary=ref_summary,
                research=gemini_research,
            )
        else:
            body = groq_body(
                seo_title,
                keyword,
                min_chars=min_c,
                max_chars=max_c,
                reference_summary=ref_summary,
            )
        body = normalize_draft_body(body.strip())
        if body.startswith("```"):
            body = re.sub(r"^```(?:markdown|md)?\s*", "", body)
            body = re.sub(r"\s*```$", "", body)
        if not body.startswith("# "):
            body = f"# {seo_title}\n\n{body}"
        if not skip_polish:
            body = gemini_polish(seo_title, keyword, body) if use_gemini else groq_polish(
                seo_title, keyword, body
            )
        body = insert_image_placeholders(body, img_count)
        errors = quality_check(body, seo_cfg)
        if len(body) >= min_c * 0.85 and not any(
            "부족" in e or "반말" in e for e in errors
        ):
            break
        if attempt == 0:
            seo_title = titles[1] if len(titles) > 1 else seo_title

    meta_tags = gemini_meta(seo_title, keyword) if use_gemini else groq_meta(seo_title, keyword)
    title = extract_title(body)
    draft_id = _draft_id(keyword)
    out_dir = DRAFTS_DIR / draft_id
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)

    status = "review" if errors else "draft_ready"
    meta = {
        "draft_id": draft_id,
        "keyword": keyword,
        "title": title,
        "seo_title": seo_title,
        "title_candidates": titles,
        "category": category,
        "related_keywords": research.get("related_keywords", []),
        "search_volume": research.get("search_volume", 0),
        "competition": research.get("competition", "unknown"),
        "blog_document_count": research.get("blog_document_count", 0),
        "research_model": research.get("research_model"),
        "gemini_research": gemini_research,
        "references": refs,
        "meta_description": meta_tags.get("meta_description", ""),
        "tags": meta_tags.get("tags", ""),
        "status": status,
        "quality_errors": errors,
        "char_count": len(body),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "published_at": None,
        "naver_url": None,
        "content_model": "gemini-2.5-flash-lite" if use_gemini else "groq",
    }

    with (out_dir / "meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    header = f"> 자동 생성 초안 · {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
    with (out_dir / "body.md").open("w", encoding="utf-8") as f:
        f.write(header + body + "\n")

    return out_dir
