"""Gemini vs Llama 4 Scout — 다른 주제 1500~2500자 비교."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from _paths import ROOT, SAMPLES

# project root via _paths
load_dotenv(ROOT / ".env")
sys.stdout.reconfigure(encoding="utf-8")

# 이전 테스트(제주도 맛집)와 다른 주제
KEYWORD = "재택근무 집중법"
SEO_TITLE = "재택근무 집중 잘하는 방법 | WFH 생산성 7가지"
MIN_CHARS = 1500
MAX_CHARS = 2500

SYSTEM = (
    "너는 한국어 SEO 블로그 본문을 작성하는 전문 작가야. "
    "글은 H1 다음 바로 읽히는 자연스러운 도입 문단으로 시작하고, "
    "'## 도입' 같은 양식 섹션은 절대 쓰지 마. 반말 금지. "
    "추론 과정은 출력하지 말고 최종 글만 작성해."
)

PROMPT = f"""다음 SEO 블로그 글을 마크다운으로 작성해줘.

- 제목(H1): {SEO_TITLE}
- 핵심 키워드: {KEYWORD}
- 분량: {MIN_CHARS}~{MAX_CHARS}자 (공백 포함) — 반드시 {MIN_CHARS}자 이상
- 시작: H1 바로 아래 2~3문단 (섹션 제목 없이)
- 본문: ## 섹션 2~3개 → 실용 팁 → 체크리스트 → FAQ 1~2개 → 마무리 질문 + #해시태그 3개+
- 금지: "## 도입", 반복 문장, 추측·과장
- 톤: 존댓말 (~습니다)
- 마크다운만 출력
"""

OUT_DIR = SAMPLES / "body_2000" / "topic_wfh"
MODELS = [
    ("gemini-3.1-flash-lite", "gemini", "Gemini 3.1 Flash Lite"),
    ("meta-llama/llama-4-scout-17b-16e-instruct", "groq", "Llama 4 Scout 17B"),
]


def slug(model_id: str) -> str:
    return model_id.replace("/", "_").replace(".", "-")


def call_gemini(model_id: str) -> tuple[str, dict]:
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        model_id,
        system_instruction=SYSTEM,
        generation_config=genai.GenerationConfig(temperature=0.6, max_output_tokens=4096),
    )
    r = model.generate_content(PROMPT)
    return (r.text or "").strip(), {"finish": "stop", "completion_tokens": None}


def call_groq(model_id: str) -> tuple[str, dict]:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        timeout=120.0,
    )
    r = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT}],
        temperature=0.6,
        max_tokens=4096,
    )
    msg = r.choices[0].message
    usage = r.usage
    return (msg.content or "").strip(), {
        "finish": r.choices[0].finish_reason,
        "completion_tokens": usage.completion_tokens if usage else None,
    }


def main() -> None:
    import json

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"주제: {KEYWORD}\n목표: {MIN_CHARS}~{MAX_CHARS}자\n", flush=True)

    for model_id, provider, label in MODELS:
        print(f"=== {label} ===", flush=True)
        start = time.perf_counter()
        try:
            if provider == "gemini":
                content, meta = call_gemini(model_id)
            else:
                content, meta = call_groq(model_id)
            elapsed = time.perf_counter() - start
            cl = len(content)
            ok = MIN_CHARS <= cl <= MAX_CHARS
            path = OUT_DIR / f"{slug(model_id)}.md"
            header = (
                f"<!-- provider: {provider} | model: {model_id} | topic: {KEYWORD} | "
                f"chars: {cl} | target: {MIN_CHARS}~{MAX_CHARS} | elapsed: {elapsed:.2f}s -->\n\n"
            )
            path.write_text(header + content, encoding="utf-8")
            print(
                f"  {elapsed:.2f}s | {cl}자 | {'OK' if ok else 'MISS'} | "
                f"tok={meta.get('completion_tokens')} -> {path.name}",
                flush=True,
            )
            results.append(
                {
                    "model": model_id,
                    "label": label,
                    "provider": provider,
                    "elapsed_sec": round(elapsed, 2),
                    "content_len": cl,
                    "in_target": ok,
                    "completion_tokens": meta.get("completion_tokens"),
                    "path": str(path.relative_to(ROOT)),
                }
            )
        except Exception as e:
            print(f"  FAIL: {e}", flush=True)
            results.append({"model": model_id, "label": label, "ok": False, "error": str(e)[:200]})

    summary_path = OUT_DIR / "results.json"
    summary_path.write_text(
        json.dumps(
            {"keyword": KEYWORD, "seo_title": SEO_TITLE, "target": f"{MIN_CHARS}~{MAX_CHARS}", "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n저장: {OUT_DIR.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
