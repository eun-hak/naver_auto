"""2000~3000자 블로그 본문 생성 모델 비교 벤치마크."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local")
sys.stdout.reconfigure(encoding="utf-8")

OUT_JSON = ROOT / "scripts" / "body_2500_benchmark_results.json"

KEYWORD = "제주도 맛집"
SEO_TITLE = "제주도 맛집 추천 | 현지인이 알려주는 BEST 10"
MIN_CHARS = 2000
MAX_CHARS = 3000

SYSTEM = (
    "너는 한국어 SEO 블로그 본문을 작성하는 전문 작가야. "
    "글은 H1 다음 바로 읽히는 자연스러운 도입 문단으로 시작하고, "
    "'## 도입' 같은 양식 섹션은 절대 쓰지 마. 반말 금지. "
    "추론 과정은 출력하지 말고 최종 글만 작성해."
)

PROMPT = f"""다음 SEO 블로그 글을 마크다운으로 작성해줘.

- 제목(H1): {SEO_TITLE}
- 핵심 키워드: {KEYWORD}
- 분량: {MIN_CHARS}~{MAX_CHARS}자 (공백 포함)
- 시작: H1 바로 아래 2~3문단을 일반 단락으로 자연스럽게 쓸 것 (섹션 제목 없이)
- 본문: 주제별 ## 섹션 2~3개 → 체크리스트 → FAQ 1~2개 → 마무리
- 금지: "## 도입", "## 핵심 한 줄", "### 도입" 같은 메타/템플릿 섹션 제목
- 톤: **전체 존댓말** (~습니다, ~입니다, ~더군요, ~드릴게요)
- 마무리: 독자 질문(존댓말) + #해시태그 3개 이상
- 마크다운만 출력 (코드블록·추론 과정 없이)
"""

MAX_TOKENS = 4096


@dataclass
class ModelSpec:
    id: str
    provider: str
    label: str
    extra: dict = field(default_factory=dict)


MODELS = [
    ModelSpec("llama-3.1-8b-instant", "groq", "Llama 3.1 8B Instant"),
    ModelSpec("qwen/qwen3-32b", "groq", "Qwen3 32B", {"reasoning_format": "hidden"}),
    ModelSpec("llama-3.3-70b-versatile", "groq", "Llama 3.3 70B Versatile"),
    ModelSpec("meta-llama/llama-4-scout-17b-16e-instruct", "groq", "Llama 4 Scout 17B"),
    ModelSpec("gemini-2.5-flash-lite", "gemini", "Gemini 2.5 Flash Lite"),
    ModelSpec("gemini-3.1-flash-lite", "gemini", "Gemini 3.1 Flash Lite"),
    ModelSpec("gemma-4-26b-a4b-it", "gemini", "Gemma 4 26B"),
    ModelSpec("gemma-4-31b-it", "gemini", "Gemma 4 31B"),
    ModelSpec("meta/llama-4-maverick-17b-128e-instruct", "nvidia", "Llama 4 Maverick 17B"),
    ModelSpec("meta/llama-3.1-8b-instruct", "nvidia", "Llama 3.1 8B Instruct"),
    ModelSpec("meta/llama-3.3-70b-instruct", "nvidia", "Llama 3.3 70B Instruct"),
    ModelSpec("google/gemma-4-31b-it", "nvidia", "Gemma 4 31B (NIM)"),
    ModelSpec("qwen/qwen3-next-80b-a3b-instruct", "nvidia", "Qwen3 Next 80B"),
    ModelSpec("meta/llama-3.1-70b-instruct", "nvidia", "Llama 3.1 70B Instruct"),
]


def korean_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(re.findall(r"[가-힣]", text)) / max(len(text.replace(" ", "")), 1)


def structure_score(text: str) -> float:
    s = 0.0
    if re.search(r"^#\s+", text, re.M):
        s += 3
    sections = len(re.findall(r"^##\s+", text, re.M))
    if sections >= 2:
        s += 4
    elif sections >= 1:
        s += 2
    if re.search(r"^[-*]\s+", text, re.M):
        s += 2
    if "#" in text and re.search(r"#\S", text):
        s += 1
    return s


def length_score(char_len: int) -> float:
    if 2000 <= char_len <= 3000:
        return 15.0
    if 1800 <= char_len < 2000 or 3000 < char_len <= 3500:
        return 10.0
    if 1500 <= char_len < 1800 or 3500 < char_len <= 4000:
        return 6.0
    if char_len >= 800:
        return 3.0
    return 0.0


def total_score(result: dict) -> float:
    if not result.get("ok"):
        return 0.0
    text = result.get("content", "")
    cl = result.get("content_len", 0)
    if result.get("reasoning_only"):
        return 0.0
    s = length_score(cl)
    s += min(10, korean_ratio(text) * 12)
    s += structure_score(text)
    s += min(5, max(0, 5 - result.get("elapsed_sec", 5) / 15))
    if re.search(r"\*?\s*Input:", text[:500]) or (
        korean_ratio(text) < 0.25 and re.search(r"[a-zA-Z]{30,}", text[:400])
    ):
        s *= 0.4
    return round(s, 1)


def _groq(spec: ModelSpec) -> dict:
    from openai import OpenAI

    key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=180.0)
    kwargs = {
        "model": spec.id,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0.6,
        "max_tokens": MAX_TOKENS,
    }
    if spec.extra.get("reasoning_format"):
        kwargs["extra_body"] = {"reasoning_format": spec.extra["reasoning_format"]}
    r = client.chat.completions.create(**kwargs)
    msg = r.choices[0].message
    return {
        "content": (msg.content or "").strip(),
        "reasoning": (getattr(msg, "reasoning_content", None) or "").strip(),
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
    }


def _nvidia(spec: ModelSpec) -> dict:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=300.0,
    )
    r = client.chat.completions.create(
        model=spec.id,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ],
        temperature=0.6,
        top_p=0.95,
        max_tokens=MAX_TOKENS,
    )
    msg = r.choices[0].message
    timing = (r.model_dump().get("nvext") or {}).get("timing") or {}
    return {
        "content": (msg.content or "").strip(),
        "reasoning": (getattr(msg, "reasoning_content", None) or "").strip(),
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
        "ttft_ms": timing.get("ttft_ms"),
        "total_ms": timing.get("total_time_ms"),
    }


def _gemini(spec: ModelSpec) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        spec.id,
        system_instruction=SYSTEM,
        generation_config=genai.GenerationConfig(
            temperature=0.6,
            max_output_tokens=MAX_TOKENS,
        ),
    )
    r = model.generate_content(PROMPT)
    return {
        "content": (r.text or "").strip(),
        "reasoning": "",
        "finish": "stop",
        "completion_tokens": None,
    }


def bench_one(spec: ModelSpec) -> dict:
    start = time.perf_counter()
    try:
        if spec.provider == "groq":
            raw = _groq(spec)
        elif spec.provider == "nvidia":
            raw = _nvidia(spec)
        else:
            raw = _gemini(spec)
        elapsed = time.perf_counter() - start
        content = raw["content"]
        reasoning = raw["reasoning"]
        result = {
            "ok": True,
            "elapsed_sec": round(elapsed, 2),
            "finish": raw["finish"],
            "completion_tokens": raw.get("completion_tokens"),
            "content_len": len(content),
            "reasoning_len": len(reasoning),
            "reasoning_only": bool(reasoning) and not content,
            "korean_ratio": round(korean_ratio(content), 3),
            "h2_count": len(re.findall(r"^##\s+", content, re.M)),
            "in_target_len": 2000 <= len(content) <= 3000,
            "preview": content[:250],
            "content": content,
            "ttft_ms": raw.get("ttft_ms"),
            "total_ms": raw.get("total_ms"),
        }
        result["score"] = total_score(result)
        return result
    except Exception as e:
        return {
            "ok": False,
            "elapsed_sec": round(time.perf_counter() - start, 2),
            "error": str(e)[:200],
            "score": 0.0,
        }


def run() -> dict:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_chars": f"{MIN_CHARS}~{MAX_CHARS}",
        "keyword": KEYWORD,
        "seo_title": SEO_TITLE,
        "models": [],
    }
    for i, spec in enumerate(MODELS, 1):
        print(f"[{i}/{len(MODELS)}] {spec.provider}/{spec.id}", flush=True)
        r = bench_one(spec)
        entry = {
            "id": spec.id,
            "provider": spec.provider,
            "label": spec.label,
            "result": {k: v for k, v in r.items() if k != "content"},
        }
        report["models"].append(entry)
        if r.get("ok"):
            print(
                f"  OK {r['elapsed_sec']}s len={r['content_len']} "
                f"target={'✓' if r.get('in_target_len') else '✗'} "
                f"score={r['score']} tok={r.get('completion_tokens')}",
                flush=True,
            )
        else:
            print(f"  FAIL {r.get('error', '')[:80]}", flush=True)
        time.sleep(0.5)

    ranked = sorted(
        report["models"],
        key=lambda m: m["result"].get("score", 0),
        reverse=True,
    )
    report["ranking"] = [
        {
            "rank": i + 1,
            "provider": m["provider"],
            "label": m["label"],
            "id": m["id"],
            "score": m["result"].get("score", 0),
            "content_len": m["result"].get("content_len"),
            "elapsed_sec": m["result"].get("elapsed_sec"),
            "in_target_len": m["result"].get("in_target_len", False),
        }
        for i, m in enumerate(ranked)
    ]
    return report


if __name__ == "__main__":
    data = run()
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT_JSON}", flush=True)
    print("\n=== 2000~3000자 본문 순위 ===", flush=True)
    for row in data["ranking"]:
        mark = "✓" if row.get("in_target_len") else " "
        print(
            f"  {row['rank']}. [{row['provider']}] {row['label']} — "
            f"{row['score']}점, {row['content_len']}자 [{mark}], {row['elapsed_sec']}s",
            flush=True,
        )
