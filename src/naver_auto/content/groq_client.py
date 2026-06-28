"""Groq API 클라이언트 (OpenAI 호환)."""

from __future__ import annotations

import json
import os
import re
import time
import zlib

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


# 글마다 다른 흐름을 쓰도록 — 키워드별로 안정적으로 하나를 골라 쓴다.
BODY_ARCHETYPES = [
    "경험·사례로 자연스럽게 시작 → 핵심 포인트 2~3개를 ## 섹션으로 → 실전 팁 한 묶음 → 짧은 마무리 (체크리스트·FAQ 없이)",
    "독자의 고민이나 질문을 던지며 시작 → 단계별 설명을 ## 섹션으로 → 자주 묻는 질문 2개(FAQ) → 한 줄 정리",
    "결론·핵심을 먼저 제시(두괄식) → 이유와 근거를 ## 섹션으로 → 비교나 실제 사례 → 자연스러운 권유 (FAQ 생략)",
    "상황에 공감하는 도입 → 장단점·선택지를 ## 섹션으로 풀어쓰기 → 추천/선택 가이드 → 마무리 질문 하나",
    "간단한 배경 설명으로 시작 → 주제별 ## 섹션 3개 → 체크리스트 한 번 → 부드러운 마무리 (FAQ 없이)",
    "친근한 한두 문장 도입 → ## 섹션으로 정보 정리 → 주의할 점이나 팁 → FAQ 1개와 짧은 마무리",
]


def pick_body_archetype(keyword: str) -> str:
    """키워드마다 다른(그러나 재현 가능한) 글 구조 원형을 고른다."""
    if not keyword:
        return BODY_ARCHETYPES[0]
    idx = zlib.crc32(keyword.strip().encode("utf-8")) % len(BODY_ARCHETYPES)
    return BODY_ARCHETYPES[idx]


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

    archetype = pick_body_archetype(focus_keyword)

    prompt = f"""다음 SEO 블로그 글을 마크다운으로 작성해줘.

- 제목(H1): {question_text}
- 핵심 키워드: {focus_keyword}
- 분량: {min_chars}~{max_chars}자 (공백 포함)
- 톤: **전체 존댓말** (~습니다, ~입니다, ~더군요, ~드릴게요)

[이번 글의 흐름 제안 — 그대로 베끼지 말고 주제에 맞게 변형]
{archetype}

[양산형 금지 — 가장 중요]
- 매번 똑같은 틀(도입 → 섹션 → 체크리스트 → FAQ → 마무리 질문)을 기계적으로 반복하지 말 것.
- 체크리스트·FAQ·마무리 질문은 주제에 자연스러울 때만, 글마다 넣는 요소와 순서를 다르게 할 것. 셋 다 넣을 필요 없음.
- 도입부를 매번 같은 인사("안녕하세요")나 같은 패턴으로 열지 말 것. 사례·질문·결론·상황 묘사 등으로 다양하게 시작.
- 문단 길이도 단조롭지 않게 섞을 것.

[지켜야 할 것]
- ## 섹션 최소 2개 이상. 제목은 **공백 포함 16자 이내로 짧게**, 끝에 한 단어만 떨어지지 않게.
- FAQ를 쓸 경우: **Q1. 질문** 한 줄 / A1. 답변 한 줄 (질문·답변 중간 줄바꿈 금지)
- 글 끝에 #해시태그 3개 이상.
- 금지: "---" 구분선, "## 도입", "## 핵심 한 줄", "### 도입" 같은 메타/템플릿 섹션 제목, 반말.
{ref_block}
- 마크다운만 출력 (코드블록·추론 과정 없이)
"""
    raw = chat(
        prompt,
        system=(
            "너는 한국어 SEO 블로그 본문을 작성하는 전문 작가야. "
            "글마다 구조와 도입을 다르게 써서 양산형 느낌이 안 나게 하는 게 핵심이야. "
            "글은 H1 다음 바로 읽히는 자연스러운 도입으로 시작하고, "
            "'## 도입' 같은 양식 섹션은 절대 쓰지 마. 반말 금지. "
            "추론 과정은 출력하지 말고 최종 글만 작성해."
        ),
        model=model,
        temperature=0.85,
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
