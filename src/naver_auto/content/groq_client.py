"""Groq API 클라이언트 (OpenAI 호환)."""

from __future__ import annotations

import json
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

from naver_auto.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.local")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

MODEL_FAST = "llama-3.1-8b-instant"
MODEL_DRAFT = "qwen/qwen3-32b"
MODEL_QUALITY = "llama-3.3-70b-versatile"


def get_api_key() -> str:
    key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY 환경변수가 필요합니다.")
    return key


def create_client() -> OpenAI:
    return OpenAI(api_key=get_api_key(), base_url=GROQ_BASE_URL)


def chat(
    prompt: str,
    *,
    system: str = "너는 한국어 SEO 블로그 글을 잘 쓰는 도우미야.",
    model: str = MODEL_FAST,
    temperature: float = 0.7,
    retries: int = 4,
) -> str:
    client = create_client()
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_err = exc
            if "429" in str(exc) or "rate_limit" in str(exc).lower():
                time.sleep(4 * (attempt + 1))
                continue
            raise
    raise last_err  # type: ignore[misc]


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


def strip_model_artifacts(text: str) -> str:
    for tag in ("think", "redacted_thinking"):
        open_tag, close_tag = f"<{tag}>", f"</{tag}>"
        while open_tag in text:
            start = text.find(open_tag)
            end = text.find(close_tag, start)
            if end == -1:
                text = text[:start]
                break
            text = text[:start] + text[end + len(close_tag) :]

    lines = text.strip().splitlines()
    cleaned: list[str] = []
    seen_h1 = False
    for line in lines:
        if line.strip().startswith("# ") and not line.strip().startswith("##"):
            if seen_h1:
                continue
            seen_h1 = True
        cleaned.append(line)
    return "\n".join(cleaned).strip()


META_SECTION_HEADING_RE = re.compile(
    r"^#{2,3}\s+(?:\*{0,2})?(?:도입(?:\s*[:：].*)?|핵심\s+한\s+줄)(?:\*{0,2})?\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def normalize_body_structure(body: str) -> str:
    lines = body.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if META_SECTION_HEADING_RE.match(line.strip()):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate_blog_body(
    question_text: str,
    focus_keyword: str,
    *,
    min_chars: int = 1500,
    max_chars: int = 3000,
    reference_summary: str = "",
    model: str = MODEL_DRAFT,
) -> str:
    ref_block = ""
    if reference_summary.strip():
        ref_block = f"\n- 참고 자료 요약 (팩트만 활용, 추측 금지):\n{reference_summary}\n"

    prompt = f"""다음 SEO 블로그 글을 마크다운으로 작성해줘.

- 제목(H1): {question_text}
- 핵심 키워드: {focus_keyword}
- 분량: {min_chars}~{max_chars}자 (공백 포함)
- 시작: H1 바로 아래 2~3문단을 일반 단락으로 자연스럽게 쓸 것 (섹션 제목 없이)
- 본문: 주제별 ## 섹션 2~3개 → 체크리스트 → FAQ 1~2개 → 마무리
- 금지: "## 도입", "## 핵심 한 줄", "### 도입" 같은 메타/템플릿 섹션 제목
- 톤: **전체 존댓말** (~습니다, ~입니다, ~더군요, ~드릴게요)
- 마무리: 독자 질문(존댓말) + #해시태그 3개 이상
{ref_block}
- 마크다운만 출력 (코드블록·추론 과정 없이)
"""
    raw = chat(
        prompt,
        system=(
            "너는 한국어 SEO 블로그 본문을 작성하는 전문 작가야. "
            "글은 H1 다음 바로 읽히는 자연스러운 도입 문단으로 시작하고, "
            "'## 도입' 같은 양식 섹션은 절대 쓰지 마. 반말 금지. "
            "추론 과정은 출력하지 말고 최종 글만 작성해."
        ),
        model=model,
        temperature=0.6,
    )
    return normalize_body_structure(strip_model_artifacts(raw))


def generate_title_candidates(
    keyword: str,
    *,
    related_keywords: list[str],
    reference_titles: list[str],
    count: int = 3,
) -> list[str]:
    related = ", ".join(related_keywords[:8]) or "(없음)"
    refs = "\n".join(f"- {t}" for t in reference_titles[:5]) or "- (없음)"
    prompt = f"""키워드 "{keyword}"에 맞는 네이버 블로그 SEO 제목 {count}개를 JSON 배열로 만들어줘.

연관 키워드: {related}
상위 블로그 제목 참고:
{refs}

규칙:
1. 35~55자, 클릭 유도 (따옴표·물음표·VS 등)
2. 키워드가 자연스럽게 포함
3. JSON만: {{"titles": ["...", "..."]}}
"""
    raw = chat(
        prompt,
        system="너는 네이버 블로그 SEO 제목 작가야. JSON만 출력.",
        model=MODEL_FAST,
        temperature=0.75,
    )
    try:
        data = parse_json_object(raw)
        titles = data.get("titles", [])
        if isinstance(titles, list):
            out = [str(t).strip() for t in titles if str(t).strip()]
            if out:
                return out[:count]
    except (ValueError, json.JSONDecodeError):
        pass
    return [f"{keyword} | 핵심 정리와 꼭 알아야 할 포인트"]


def _split_intro(body: str) -> tuple[str, str]:
    lines = body.strip().splitlines()
    if not lines:
        return "", ""

    rest_idx = len(lines)
    seen_content = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("##"):
            rest_idx = i
            break
        if stripped and not stripped.startswith("#"):
            seen_content = True
        elif (
            seen_content
            and not stripped
            and i + 1 < len(lines)
            and lines[i + 1].strip().startswith("##")
        ):
            rest_idx = i
            break

    intro = "\n".join(lines[:rest_idx]).strip()
    rest = "\n".join(lines[rest_idx:]).strip()
    return intro, rest


def polish_intro(
    seo_title: str,
    focus_keyword: str,
    body: str,
    *,
    model: str = MODEL_QUALITY,
) -> str:
    intro, rest = _split_intro(body)
    if len(intro) < 80:
        return body

    prompt = f"""아래 블로그 글의 도입부만 더 자연스럽고 읽기 좋게 다듬어줘.

- SEO 제목: {seo_title}
- 핵심 키워드: {focus_keyword}
- 규칙: H1(#) 다음 일반 문단 2~3개만 출력. ## 도입·## 핵심 한 줄 같은 섹션 제목 금지
- 존댓말 유지, 과장·clickbait 금지

[현재 도입부]
{intro}
"""
    polished = chat(
        prompt,
        system="너는 한국어 SEO 블로그 도입부를 다듬는 편집자야.",
        model=model,
        temperature=0.45,
    ).strip()

    if polished.startswith("```"):
        polished = re.sub(r"^```(?:markdown)?\s*", "", polished)
        polished = re.sub(r"\s*```$", "", polished).strip()

    polished = normalize_body_structure(strip_model_artifacts(polished))
    if not polished:
        return body
    merged = f"{polished}\n\n{rest}" if rest else polished
    return normalize_body_structure(merged)


def generate_meta_tags(
    seo_title: str,
    focus_keyword: str,
    *,
    model: str = MODEL_FAST,
) -> dict[str, str]:
    prompt = f"""SEO 블로그용 메타 정보를 JSON으로 만들어줘.

- 제목: {seo_title}
- 키워드: {focus_keyword}

출력 형식 (JSON만):
{{"meta_description": "120~160자", "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"]}}
"""
    raw = chat(
        prompt,
        system="너는 한국어 SEO 메타 태그 작성 도우미야. JSON만 출력.",
        model=model,
        temperature=0.5,
    ).strip()
    try:
        data = parse_json_object(raw)
    except (ValueError, json.JSONDecodeError):
        data = {}
    tags = data.get("tags", [])
    if isinstance(tags, list):
        tags_str = ", ".join(str(t) for t in tags[:5])
    else:
        tags_str = str(tags)
    return {
        "meta_description": str(data.get("meta_description", "")).strip(),
        "tags": tags_str,
    }
