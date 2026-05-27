"""네이버 검색·광고 API 키워드 분석."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from naver_auto.paths import USER_AGENT, naver_ad_configured, naver_api_configured

NAVER_SEARCH_API_BASE = "https://openapi.naver.com/v1/search"
NAVER_AD_API_BASE = "https://api.naver.com"
AUTOCOMPLETE_URL = (
    "https://ac.search.naver.com/nx/ac"
    "?q={query}&con=1&frm=nv&ans=2&r_format=json&r_enc=UTF-8"
    "&q_enc=UTF-8&st=100&r_lt=100&r_unicode=0&t_koreng=1&run=2&rev=4"
)


def _normalize_count(value: int | str) -> int:
    if isinstance(value, str) and value == "< 10":
        return 5
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def fetch_autocomplete(keyword: str) -> list[str]:
    url = AUTOCOMPLETE_URL.format(query=quote(keyword))
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.get(url, headers={"User-Agent": USER_AGENT})
            res.raise_for_status()
            data = res.json()
    except Exception:
        return []

    keywords: list[str] = []
    for group in data.get("items", []):
        if not isinstance(group, list):
            continue
        for entry in group:
            if isinstance(entry, list) and entry and isinstance(entry[0], str):
                keywords.append(entry[0])
    return keywords[:20]


def _search_headers() -> dict[str, str]:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 필요합니다.")
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def search_naver(
    query: str,
    search_type: str = "blog",
    *,
    display: int = 10,
    sort: str = "sim",
    start: int = 1,
) -> dict[str, Any]:
    params = {
        "query": query,
        "display": str(display),
        "sort": sort,
        "start": str(start),
    }
    url = f"{NAVER_SEARCH_API_BASE}/{search_type}"
    with httpx.Client(timeout=20.0) as client:
        res = client.get(url, params=params, headers=_search_headers())
        if res.status_code == 429:
            raise RuntimeError("네이버 검색 API 한도 초과")
        res.raise_for_status()
        return res.json()


def fetch_blog_total_count(keyword: str) -> int:
    if not naver_api_configured():
        return 0
    try:
        data = search_naver(keyword, "blog", display=1)
        return int(data.get("total", 0))
    except Exception:
        return 0


def _ad_signature(timestamp: str, method: str, path: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{path}"
    digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def fetch_keyword_stats(keyword: str) -> dict[str, Any]:
    if not naver_ad_configured():
        return {
            "search_volume": 0,
            "monthly_pc": 0,
            "monthly_mobile": 0,
            "competition": "unknown",
            "related_keywords": [],
            "source": "none",
        }

    path = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    secret = os.getenv("NAVER_AD_SECRET_KEY", "")
    signature = _ad_signature(timestamp, method, path, secret)
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": os.getenv("NAVER_AD_ACCESS_LICENSE", ""),
        "X-Customer": os.getenv("NAVER_AD_CUSTOMER_ID", ""),
        "X-Signature": signature,
    }
    hint = re.sub(r"\s+", "", keyword.strip())
    url = f"{NAVER_AD_API_BASE}{path}?hintKeywords={quote(hint)}&showDetail=1"

    with httpx.Client(timeout=20.0) as client:
        res = client.get(url, headers=headers)
        if res.status_code == 429:
            raise RuntimeError("네이버 검색광고 API 한도 초과")
        res.raise_for_status()
        data = res.json()

    keyword_list = data.get("keywordList", [])
    target = _normalize_keyword(keyword)
    main = next(
        (k for k in keyword_list if _normalize_keyword(k.get("relKeyword", "")) == target),
        None,
    )
    monthly_pc = _normalize_count(main.get("monthlyPcQcCnt", 0)) if main else 0
    monthly_mobile = _normalize_count(main.get("monthlyMobileQcCnt", 0)) if main else 0
    related = []
    for item in keyword_list:
        rel = str(item.get("relKeyword", "")).strip()
        if not rel or _normalize_keyword(rel) == target:
            continue
        related.append(
            {
                "keyword": rel,
                "monthly_total": _normalize_count(item.get("monthlyPcQcCnt", 0))
                + _normalize_count(item.get("monthlyMobileQcCnt", 0)),
                "competition": item.get("compIdx", "unknown"),
            }
        )

    competition = main.get("compIdx", "unknown") if main else "unknown"
    total_docs = fetch_blog_total_count(keyword)
    competition_level = _competition_level(competition, total_docs)

    return {
        "search_volume": monthly_pc + monthly_mobile,
        "monthly_pc": monthly_pc,
        "monthly_mobile": monthly_mobile,
        "competition": competition_level,
        "competition_index": competition,
        "related_keywords": related[:15],
        "blog_document_count": total_docs,
        "source": "naver_ad",
    }


def _competition_level(comp_idx: str, total_docs: int) -> str:
    if comp_idx in ("HIGH", "높음"):
        return "high"
    if comp_idx in ("MEDIUM", "중간"):
        return "medium"
    if comp_idx in ("LOW", "낮음"):
        return "low"
    if total_docs >= 500_000:
        return "high"
    if total_docs >= 50_000:
        return "medium"
    return "low"


def analyze_keyword(keyword: str) -> dict[str, Any]:
    keyword = keyword.strip()
    if not keyword:
        raise ValueError("키워드가 비어 있습니다.")

    related: list[str] = []
    blog_total = 0
    if naver_api_configured():
        related.extend(fetch_autocomplete(keyword))
        blog_total = fetch_blog_total_count(keyword)

    stats = fetch_keyword_stats(keyword)
    ad_related = [r["keyword"] for r in stats.get("related_keywords", [])]
    merged_related: list[str] = []
    seen: set[str] = set()
    for item in related + ad_related:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged_related.append(key)

    result: dict[str, Any] = {
        "keyword": keyword,
        "search_volume": stats.get("search_volume", 0),
        "monthly_pc": stats.get("monthly_pc", 0),
        "monthly_mobile": stats.get("monthly_mobile", 0),
        "competition": stats.get("competition", "unknown"),
        "competition_index": stats.get("competition_index", "unknown"),
        "related_keywords": merged_related[:15],
        "blog_document_count": stats.get("blog_document_count", blog_total),
        "status": "research_done",
        "research_model": None,
        "gemini_research": {},
    }

    if naver_api_configured() and os.getenv("GEMINI_API_KEY"):
        from naver_auto.content.gemini_client import research_keyword
        from naver_auto.keyword.references import fetch_blog_references

        refs = fetch_blog_references(keyword)
        try:
            gemini = research_keyword(keyword, naver_data=result, references=refs)
            result["gemini_research"] = gemini
            result["research_model"] = "gemini-2.5-flash-lite"
            extra = gemini.get("related_keywords", [])
            for item in extra:
                key = str(item).strip()
                if key and key not in merged_related:
                    merged_related.append(key)
            result["related_keywords"] = merged_related[:15]
        except Exception as exc:
            result["research_error"] = str(exc)

    return result
