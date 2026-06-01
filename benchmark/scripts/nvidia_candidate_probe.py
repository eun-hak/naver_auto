"""NVIDIA NIM 후보 모델 6종 — basic / SEO제목 / 본문300 프로브."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from _paths import RESULTS, ROOT

# project root via _paths
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local")
sys.stdout.reconfigure(encoding="utf-8")

OUT = RESULTS / "nvidia_candidate_probe_results.json"

MODELS = [
    ("stepfun-ai/step-3.7-flash", "Step 3.7 Flash"),
    ("z-ai/glm-5.1", "GLM 5.1"),
    ("minimaxai/minimax-m2.7", "MiniMax M2.7"),
    ("mistralai/mistral-nemotron", "Mistral Nemotron"),
    ("bytedance/seed-oss-36b-instruct", "Seed OSS 36B"),
]

PROMPTS = {
    "basic": {
        "prompt": '한국어로 "안녕하세요"라고만 답해주세요.',
        "max_tokens": 128,
        "temperature": 0.3,
    },
    "blog_title": {
        "prompt": (
            '키워드 "제주도 맛집"으로 네이버 블로그 SEO 제목 3개를 '
            'JSON 배열로만 출력하세요. 예: ["제목1", "제목2", "제목3"]'
        ),
        "max_tokens": 512,
        "temperature": 0.7,
    },
    "blog_body_300": {
        "prompt": (
            '키워드 "제주도 맛집"으로 네이버 블로그 본문 300자 분량을 작성하세요. '
            "자연스러운 한국어, SEO 친화적. 마크다운 없이 본문만."
        ),
        "max_tokens": 2048,
        "temperature": 0.7,
    },
}


def run_one(client: OpenAI, model_id: str, test_name: str) -> dict:
    cfg = PROMPTS[test_name]
    start = time.perf_counter()
    try:
        r = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": cfg["prompt"]}],
            temperature=cfg["temperature"],
            max_tokens=cfg["max_tokens"],
            top_p=0.95,
            timeout=300,
        )
        elapsed = round(time.perf_counter() - start, 2)
        msg = r.choices[0].message
        content = (msg.content or "").strip()
        reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
        usage = r.usage
        return {
            "ok": True,
            "elapsed_sec": elapsed,
            "finish": r.choices[0].finish_reason,
            "content_len": len(content),
            "reasoning_len": len(reasoning),
            "reasoning_only": bool(reasoning) and not content,
            "completion_tokens": usage.completion_tokens if usage else None,
            "preview": content[:120],
        }
    except Exception as e:
        return {
            "ok": False,
            "elapsed_sec": round(time.perf_counter() - start, 2),
            "error": str(e)[:200],
        }


def main() -> int:
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        print("ERROR: NVIDIA_API_KEY 없음 — .env에 추가 후 재실행", flush=True)
        return 1

    client = OpenAI(
        api_key=key,
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=300.0,
    )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "models": [],
    }

    for i, (model_id, label) in enumerate(MODELS, 1):
        print(f"\n[{i}/{len(MODELS)}] {label} ({model_id})", flush=True)
        entry = {"id": model_id, "label": label, "tests": {}}
        for test_name in PROMPTS:
            print(f"  {test_name}...", end=" ", flush=True)
            r = run_one(client, model_id, test_name)
            entry["tests"][test_name] = r
            if r.get("ok"):
                flag = "R-only" if r.get("reasoning_only") else "OK"
                print(
                    f"{flag} {r['elapsed_sec']}s len={r['content_len']} "
                    f"tok={r.get('completion_tokens')} | {r.get('preview', '')[:50]}",
                    flush=True,
                )
            else:
                print(f"FAIL {r.get('error', '')[:80]}", flush=True)
            time.sleep(0.3)
        report["models"].append(entry)

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
