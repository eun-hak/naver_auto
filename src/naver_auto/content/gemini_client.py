"""Gemini API 클라이언트 (조사·글 생성)."""

from __future__ import annotations

import json
import os
import re

import google.generativeai as genai

DEFAULT_MODEL = "gemini-2.5-flash-lite"


def _model_name() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def _configure() -> None:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다.")
    genai.configure(api_key=key)


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _generate(prompt: str, *, system: str = "", temperature: float = 0.7) -> str:
    _configure()
    model = genai.GenerativeModel(
        _model_name(),
        system_instruction=system or "너는 한국어 SEO 블로그 전문가야.",
    )
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(temperature=temperature),
    )
    return (response.text or "").strip()


def parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        data = json.loads(match.group())
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아닙니다.")
    return data


def research_keyword(
    keyword: str,
    *,
    naver_data: dict,
    references: list[dict],
) -> dict:
    refs_text = "\n".join(
        f"- {r.get('title', '')}: {str(r.get('description', ''))[:100]}"
        for r in references[:8]
    ) or "- (없음)"
    related = ", ".join(naver_data.get("related_keywords", [])[:12]) or "(없음)"

    prompt = f"""키워드 "{keyword}"에 대한 네이버 블로그 SEO 조사 리포트를 JSON으로 작성해.

[네이버 API 수집 데이터]
- 블로그 문서 수: {naver_data.get('blog_document_count', 0)}
- 연관 키워드: {related}
- 경쟁도: {naver_data.get('competition', 'unknown')}

[상위 블로그 참고]
{refs_text}

JSON 형식:
{{
  "search_intent": "info|howto|compare|review",
  "target_reader": "누구를 위한 글인지 한 줄",
  "content_angles": ["글에 넣을 소주제 3~5개"],
  "related_keywords": ["추천 연관키워드 5~10개"],
  "recommended_title_patterns": ["제목 패턴 2~3개"],
  "writing_brief": "글 작성 시 반드시 다룰 핵심 포인트 3~5문장",
  "competition_note": "경쟁 상황 한 줄"
}}
"""
    raw = _generate(
        prompt,
        system="너는 네이버 블로그 키워드 리서처야. JSON만 출력.",
        temperature=0.4,
    )
    return parse_json_object(raw)


def generate_title_candidates(
    keyword: str,
    *,
    related_keywords: list[str],
    reference_titles: list[str],
    research: dict | None = None,
    count: int = 3,
) -> list[str]:
    related = ", ".join(related_keywords[:8]) or "(없음)"
    refs = "\n".join(f"- {t}" for t in reference_titles[:5]) or "- (없음)"
    brief = (research or {}).get("writing_brief", "")
    patterns = (research or {}).get("recommended_title_patterns", [])

    prompt = f"""키워드 "{keyword}" 네이버 블로그 SEO 제목 {count}개를 JSON으로 만들어.

연관 키워드: {related}
상위 블로그 제목:
{refs}
조사 브리프: {brief}
추천 패턴: {', '.join(patterns) if patterns else '(없음)'}

규칙: 35~55자, 클릭 유도, 존댓말 톤에 맞는 제목
JSON: {{"titles": ["...", "..."]}}
"""
    raw = _generate(prompt, system="네이버 SEO 제목 작가. JSON만.", temperature=0.75)
    try:
        data = parse_json_object(raw)
        titles = [str(t).strip() for t in data.get("titles", []) if str(t).strip()]
        if titles:
            return titles[:count]
    except (ValueError, json.JSONDecodeError):
        pass
    return [f"{keyword} | 맛있게 만드는 방법과 꿀팁 총정리"]


def generate_blog_body(
    seo_title: str,
    focus_keyword: str,
    *,
    min_chars: int = 1500,
    max_chars: int = 3500,
    reference_summary: str = "",
    research: dict | None = None,
) -> str:
    angles = (research or {}).get("content_angles", [])
    brief = (research or {}).get("writing_brief", "")
    angles_text = "\n".join(f"- {a}" for a in angles) if angles else "- (자유)"

    prompt = f"""다음 SEO 블로그 글을 마크다운으로 작성해.

- 제목(H1): {seo_title}
- 핵심 키워드: {focus_keyword}
- 분량: {min_chars}~{max_chars}자
- 톤: **전체 존댓말** (~습니다, ~입니다)
- 구조: H1 → 도입 2~3문단 → ## 섹션 2~3개 → 체크리스트 → FAQ → 마무리 질문 + #해시태그 3개+
- 금지: "## 도입" 같은 메타 섹션 제목, 반말, 추측·과장

[조사 브리프]
{brief}

[권장 섹션]
{angles_text}

[참고 자료]
{reference_summary or '(없음)'}

마크다운만 출력.
"""
    return _generate(
        prompt,
        system="한국어 SEO 블로그 작가. 자연스러운 존댓말. 최종 글만.",
        temperature=0.6,
    )


def polish_intro(seo_title: str, focus_keyword: str, body: str) -> str:
    lines = body.strip().splitlines()
    rest_idx = len(lines)
    for i, line in enumerate(lines):
        if line.strip().startswith("##"):
            rest_idx = i
            break
    intro = "\n".join(lines[:rest_idx]).strip()
    rest = "\n".join(lines[rest_idx:]).strip()
    if len(intro) < 80:
        return body

    prompt = f"""도입부만 다듬어. H1(#) 포함, ## 섹션 제목 없이 2~3문단.
제목: {seo_title}, 키워드: {focus_keyword}
존댓말 유지.

[현재 도입부]
{intro}
"""
    polished = _generate(prompt, system="블로그 편집자.", temperature=0.45)
    if polished.startswith("```"):
        polished = re.sub(r"^```(?:markdown)?\s*", "", polished)
        polished = re.sub(r"\s*```$", "", polished).strip()
    if not polished:
        return body
    return f"{polished}\n\n{rest}" if rest else polished


def generate_meta_tags(seo_title: str, focus_keyword: str) -> dict[str, str]:
    prompt = f"""SEO 메타 JSON 작성.
제목: {seo_title}
키워드: {focus_keyword}
{{"meta_description": "120~160자", "tags": ["태그1","태그2","태그3","태그4","태그5"]}}
"""
    raw = _generate(prompt, system="SEO 메타 작성. JSON만.", temperature=0.5)
    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        data = {}
    tags = data.get("tags", [])
    tags_str = ", ".join(str(t) for t in tags[:5]) if isinstance(tags, list) else str(tags)
    return {
        "meta_description": str(data.get("meta_description", "")).strip(),
        "tags": tags_str,
    }


def plan_image_slots(
    keyword: str,
    title: str,
    slots: list[dict],
    *,
    body_excerpt: str = "",
) -> list[dict]:
    """슬롯별 네이버 이미지 검색어·alt·Gemini 프롬프트 (1회 호출)."""
    slots_json = json.dumps(slots, ensure_ascii=False, indent=2)
    prompt = f"""블로그 글의 이미지 슬롯별 검색 계획을 JSON으로 작성해.

키워드: {keyword}
제목: {title}

슬롯 (소제목 기준):
{slots_json}

본문 발췌:
{body_excerpt[:2000]}

JSON 형식 (slots 배열만):
{{
  "slots": [
    {{
      "slot": 1,
      "section": "소제목",
      "search_query": "네이버 이미지 검색용 2~6단어",
      "alt": "이미지 설명 10~30자",
      "gemini_prompt": "English food photo prompt, no text overlay"
    }}
  ]
}}

규칙:
- search_query: 구체적 음식명·지역명·메뉴명 (예: 강화도 순무탕수육, 깐풍기 중국요리)
- 슬롯마다 search_query를 다르게
- 아이콘·일러스트·앱 UI 검색어 금지
- gemini_prompt: 실사 음식 사진 스타일
"""
    raw = _generate(
        prompt,
        system="한국어 블로그 이미지 기획자. JSON만 출력.",
        temperature=0.4,
    )
    data = parse_json_object(raw)
    items = data.get("slots", data if isinstance(data, list) else [])
    if not isinstance(items, list):
        raise ValueError("slots 배열이 없습니다.")

    by_slot = {int(s["slot"]): s for s in slots if "slot" in s}
    merged: list[dict] = []
    for item in items:
        if not isinstance(item, dict) or "slot" not in item:
            continue
        slot = int(item["slot"])
        base = by_slot.get(slot, {})
        merged.append(
            {
                "slot": slot,
                "section": str(item.get("section") or base.get("section", "")),
                "search_query": str(item.get("search_query") or base.get("section") or keyword)[
                    :60
                ],
                "alt": str(item.get("alt") or base.get("alt") or base.get("section", ""))[:80],
                "gemini_prompt": str(
                    item.get("gemini_prompt")
                    or f"{base.get('section', keyword)} food photo, no text"
                )[:200],
            }
        )
    merged.sort(key=lambda x: x["slot"])
    if not merged:
        raise ValueError("유효한 슬롯 계획 없음")
    return merged
