"""4000~5000자 본문 TOP 4 모델 샘플 생성."""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from _paths import RESULTS, ROOT, SAMPLES

# project root via _paths
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local")
sys.stdout.reconfigure(encoding="utf-8")

OUT_DIR = SAMPLES / "body_4500"
OUT_JSON = RESULTS / "body_4500_benchmark_results.json"

KEYWORD = "제주도 맛집"
SEO_TITLE = "제주도 맛집 추천 | 현지인이 알려주는 BEST 10"
MIN_CHARS = 4000
MAX_CHARS = 5000
MAX_TOKENS = 8192

SYSTEM = (
    "너는 한국어 SEO 블로그 본문을 작성하는 전문 작가야. "
    "글은 H1 다음 바로 읽히는 자연스러운 도입 문단으로 시작하고, "
    "'## 도입' 같은 양식 섹션은 절대 쓰지 마. 반말 금지. "
    "추론 과정은 출력하지 말고 최종 글만 작성해."
)

PROMPT = f"""다음 SEO 블로그 글을 마크다운으로 작성해줘.

- 제목(H1): {SEO_TITLE}
- 핵심 키워드: {KEYWORD}
- 분량: {MIN_CHARS}~{MAX_CHARS}자 (공백 포함) — 반드시 이 범위를 지켜줘
- 시작: H1 바로 아래 2~3문단을 일반 단락으로 자연스럽게 쓸 것 (섹션 제목 없이)
- 본문: 주제별 ## 섹션 3~4개 → 각 섹션마다 구체적인 맛집·메뉴 설명 → 체크리스트 → FAQ 2~3개 → 마무리
- 금지: "## 도입", "## 핵심 한 줄", "### 도입" 같은 메타/템플릿 섹션 제목
- 톤: **전체 존댓말** (~습니다, ~입니다, ~더군요, ~드릴게요)
- 마무리: 독자 질문(존댓말) + #해시태그 3개 이상
- 마크다운만 출력 (코드블록·추론 과정 없이)
"""


@dataclass
class ModelSpec:
    id: str
    provider: str
    label: str
    extra: dict = field(default_factory=dict)


TOP4 = [
    ModelSpec("gemini-3.1-flash-lite", "gemini", "Gemini 3.1 Flash Lite"),
    ModelSpec("meta/llama-3.1-8b-instruct", "nvidia", "Llama 3.1 8B Instruct"),
    ModelSpec("llama-3.1-8b-instant", "groq", "Llama 3.1 8B Instant"),
    ModelSpec("qwen/qwen3-next-80b-a3b-instruct", "nvidia", "Qwen3 Next 80B"),
]


def _groq(spec: ModelSpec) -> dict:
    from openai import OpenAI
    import os

    key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=300.0)
    # Groq TPM 한도: 8192 max_tokens 요청 시 413 발생 → 4096 사용
    r = client.chat.completions.create(
        model=spec.id,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT}],
        temperature=0.6,
        max_tokens=4096,
    )
    msg = r.choices[0].message
    return {
        "content": (msg.content or "").strip(),
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
    }


def _nvidia(spec: ModelSpec) -> dict:
    from openai import OpenAI
    import os

    client = OpenAI(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=600.0,
    )
    r = client.chat.completions.create(
        model=spec.id,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT}],
        temperature=0.6,
        top_p=0.95,
        max_tokens=MAX_TOKENS,
    )
    msg = r.choices[0].message
    return {
        "content": (msg.content or "").strip(),
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
    }


def _gemini(spec: ModelSpec) -> dict:
    import google.generativeai as genai
    import os

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        spec.id,
        system_instruction=SYSTEM,
        generation_config=genai.GenerationConfig(temperature=0.6, max_output_tokens=MAX_TOKENS),
    )
    r = model.generate_content(PROMPT)
    return {"content": (r.text or "").strip(), "finish": "stop", "completion_tokens": None}


def generate(spec: ModelSpec) -> dict:
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
        cl = len(content)
        return {
            "ok": True,
            "elapsed_sec": round(elapsed, 2),
            "finish": raw["finish"],
            "completion_tokens": raw.get("completion_tokens"),
            "content_len": cl,
            "in_target_len": 4000 <= cl <= 5000,
            "h2_count": len(re.findall(r"^##\s+", content, re.M)),
            "content": content,
        }
    except Exception as e:
        return {"ok": False, "elapsed_sec": round(time.perf_counter() - start, 2), "error": str(e)[:200]}


def slug(model_id: str) -> str:
    return model_id.replace("/", "_").replace(".", "-")


def main() -> None:
    import json
    from datetime import datetime, timezone

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "target": "4000~5000", "models": []}

    for spec in TOP4:
        print(f"\n=== {spec.label} ({spec.provider}) ===", flush=True)
        r = generate(spec)
        entry = {"id": spec.id, "provider": spec.provider, "label": spec.label, "result": {}}
        if r.get("ok"):
            mark = "✓" if r["in_target_len"] else "✗"
            print(
                f"  {r['elapsed_sec']}s | {r['content_len']}자 [{mark}] | "
                f"tok={r.get('completion_tokens')} | H2={r['h2_count']} | finish={r['finish']}",
                flush=True,
            )
            path = OUT_DIR / f"{slug(spec.id)}.md"
            meta = (
                f"<!-- provider: {spec.provider} | model: {spec.id} | "
                f"chars: {r['content_len']} | target: 4000~5000 | elapsed: {r['elapsed_sec']}s -->\n\n"
            )
            path.write_text(meta + r["content"], encoding="utf-8")
            print(f"  -> {path.relative_to(ROOT)}", flush=True)
            entry["result"] = {k: v for k, v in r.items() if k != "content"}
        else:
            print(f"  FAIL: {r.get('error')}", flush=True)
            entry["result"] = r
        report["models"].append(entry)

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON: {OUT_JSON.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
