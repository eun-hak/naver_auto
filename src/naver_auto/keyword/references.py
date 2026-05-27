"""네이버 블로그 검색 API 참고 자료 수집."""

from __future__ import annotations

from typing import Any

from naver_auto.keyword.analyzer import search_naver
from naver_auto.paths import naver_api_configured


def fetch_blog_references(keyword: str, *, limit: int = 5) -> list[dict[str, Any]]:
    if not naver_api_configured():
        return []

    data = search_naver(keyword, "blog", display=limit, sort="sim")
    refs: list[dict[str, Any]] = []
    for item in data.get("items", []):
        title = str(item.get("title", "")).replace("<b>", "").replace("</b>", "")
        description = str(item.get("description", "")).replace("<b>", "").replace("</b>", "")
        refs.append(
            {
                "title": title,
                "description": description,
                "link": item.get("link", ""),
                "blogger": item.get("bloggername", ""),
            }
        )
    return refs


def summarize_references(refs: list[dict[str, Any]]) -> str:
    if not refs:
        return ""
    lines: list[str] = []
    for ref in refs[:5]:
        title = ref.get("title", "")
        desc = ref.get("description", "")
        lines.append(f"- {title}: {desc[:120]}")
    return "\n".join(lines)


def reference_titles(refs: list[dict[str, Any]]) -> list[str]:
    return [str(r.get("title", "")).strip() for r in refs if r.get("title")]
