"""NVIDIA NIM — mistral-nemotron / step-3.7-flash 1500~2500자 본문 테스트."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from _paths import RESULTS, ROOT, SAMPLES

# project root via _paths
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local")
sys.stdout.reconfigure(encoding="utf-8")

KEYWORD = "제주도 맛집"
SEO_TITLE = "제주도 맛집 추천 | 현지인이 알려주는 BEST 10"
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

OUT_DIR = SAMPLES / "body_2000" / "nvidia_candidates"
OUT_JSON = RESULTS / "nvidia_two_models_1500_2500_results.json"

MODELS = [
    ("stepfun-ai/step-3.7-flash", "Step 3.7 Flash"),
    ("mistralai/mistral-nemotron", "Mistral Nemotron"),
]


def slug(model_id: str) -> str:
    return model_id.replace("/", "_").replace(".", "-")


def call_nvidia(client: OpenAI, model_id: str) -> tuple[str, dict]:
    r = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ],
        temperature=0.6,
        top_p=0.95,
        max_tokens=4096,
        timeout=300,
    )
    msg = r.choices[0].message
    content = (msg.content or "").strip()
    reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
    usage = r.usage
    timing = (r.model_dump().get("nvext") or {}).get("timing") or {}
    return content, {
        "finish": r.choices[0].finish_reason,
        "completion_tokens": usage.completion_tokens if usage else None,
        "reasoning_len": len(reasoning),
        "reasoning_only": bool(reasoning) and not content,
        "ttft_ms": timing.get("ttft_ms"),
        "total_ms": timing.get("total_time_ms"),
    }


def main() -> int:
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        print("ERROR: NVIDIA_API_KEY 없음", flush=True)
        return 1

    client = OpenAI(
        api_key=key,
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=300.0,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"주제: {KEYWORD}\n목표: {MIN_CHARS}~{MAX_CHARS}자\n", flush=True)

    for i, (model_id, label) in enumerate(MODELS, 1):
        print(f"[{i}/{len(MODELS)}] {label} ({model_id})", flush=True)
        start = time.perf_counter()
        try:
            content, meta = call_nvidia(client, model_id)
            elapsed = time.perf_counter() - start
            cl = len(content)
            ok = MIN_CHARS <= cl <= MAX_CHARS
            path = OUT_DIR / f"{slug(model_id)}.md"
            header = (
                f"<!-- provider: nvidia | model: {model_id} | topic: {KEYWORD} | "
                f"chars: {cl} | target: {MIN_CHARS}~{MAX_CHARS} | elapsed: {elapsed:.2f}s -->\n\n"
            )
            path.write_text(header + content, encoding="utf-8")
            status = "OK" if ok else "MISS"
            if meta.get("reasoning_only"):
                status = "R-only"
            print(
                f"  {status} {elapsed:.2f}s | {cl}자 | tok={meta.get('completion_tokens')} | "
                f"finish={meta.get('finish')} -> {path.name}",
                flush=True,
            )
            if content:
                print(f"  preview: {content[:120].replace(chr(10), ' ')}", flush=True)
            results.append(
                {
                    "model": model_id,
                    "label": label,
                    "elapsed_sec": round(elapsed, 2),
                    "content_len": cl,
                    "in_target": ok,
                    "reasoning_only": meta.get("reasoning_only"),
                    "completion_tokens": meta.get("completion_tokens"),
                    "finish": meta.get("finish"),
                    "ttft_ms": meta.get("ttft_ms"),
                    "path": str(path.relative_to(ROOT)),
                }
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            print(f"  FAIL {elapsed:.2f}s: {e}", flush=True)
            results.append(
                {
                    "model": model_id,
                    "label": label,
                    "ok": False,
                    "elapsed_sec": round(elapsed, 2),
                    "error": str(e)[:200],
                }
            )
        time.sleep(0.3)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "keyword": KEYWORD,
        "seo_title": SEO_TITLE,
        "target": f"{MIN_CHARS}~{MAX_CHARS}",
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT_DIR.relative_to(ROOT)}", flush=True)
    print(f"결과: {OUT_JSON.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
