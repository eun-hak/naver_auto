"""NVIDIA NIM 추가 후보 - 빠른 프로브 + 선별 벤치."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
sys.stdout.reconfigure(encoding="utf-8")

client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=os.getenv("NVIDIA_API_KEY"), timeout=45.0)

PROMPTS = {
    "basic": '한국어로 "안녕하세요"라고만 답해주세요.',
    "blog_title": (
        '키워드 "제주도 맛집"으로 네이버 블로그 SEO 제목 3개를 '
        'JSON 배열로만 출력하세요. 예: ["제목1", "제목2", "제목3"]'
    ),
    "blog_body": (
        '키워드 "제주도 맛집"으로 네이버 블로그 본문 300자 분량을 작성하세요. '
        "자연스러운 한국어, SEO 친화적. 마크다운 없이 본문만."
    ),
}

EXTRA = [
    "google/gemma-3-12b-it",
    "google/gemma-4-31b-it",
    "mistralai/mistral-large-3-675b-instruct-2512",
    "mistralai/mistral-medium-3.5-128b",
    "mistralai/mistral-large-2-instruct",
    "mistralai/mistral-7b-instruct-v0.3",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "qwen/qwen3.5-122b-a10b",
    "qwen/qwen3-next-80b-a3b-instruct",
    "deepseek-ai/deepseek-v4-flash",
    "meta/llama-4-maverick-17b-128e-instruct",
    "stepfun-ai/step-3.5-flash",
    "z-ai/glm-5.1",
    "moonshotai/kimi-k2.6",
    "openai/gpt-oss-20b",
    "upstage/solar-10.7b-instruct",
    "01-ai/yi-large",
    "bytedance/seed-oss-36b-instruct",
]


def probe(model: str) -> dict:
    start = time.perf_counter()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPTS["basic"]}],
            temperature=0.3,
            max_tokens=32,
        )
        msg = r.choices[0].message
        content = (msg.content or "").strip()
        reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
        return {
            "model": model,
            "ok": True,
            "probe_sec": round(time.perf_counter() - start, 2),
            "content": content[:40],
            "reasoning": bool(reasoning),
            "reasoning_only": bool(reasoning) and not content,
        }
    except Exception as e:
        return {"model": model, "ok": False, "probe_sec": round(time.perf_counter() - start, 2), "error": str(e)[:100]}


def bench(model: str) -> dict:
    out = {"model": model, "tests": {}}
    for name, prompt in PROMPTS.items():
        max_tokens = 64 if name == "basic" else (400 if name == "blog_title" else 800)
        start = time.perf_counter()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7 if name != "basic" else 0.3,
                max_tokens=max_tokens,
            )
            elapsed = time.perf_counter() - start
            msg = r.choices[0].message
            content = (msg.content or "").strip()
            reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
            out["tests"][name] = {
                "ok": True,
                "elapsed_sec": round(elapsed, 2),
                "finish": r.choices[0].finish_reason,
                "completion_tokens": r.usage.completion_tokens if r.usage else None,
                "content_len": len(content),
                "reasoning_only": bool(reasoning) and not content,
                "preview": content[:150],
            }
        except Exception as e:
            out["tests"][name] = {"ok": False, "elapsed_sec": round(time.perf_counter() - start, 2), "error": str(e)[:120]}
    return out


if __name__ == "__main__":
    print("=== 프로브 ===", flush=True)
    probes = [probe(m) for m in EXTRA]
    for p in probes:
        if p.get("ok"):
            note = " [R]" if p.get("reasoning") else ""
            print(f"OK({p['probe_sec']}s){note} {p['model']}: {p.get('content')}", flush=True)
        else:
            print(f"FAIL({p['probe_sec']}s) {p['model']}: {p.get('error')}", flush=True)

    ok = [
        p["model"]
        for p in probes
        if p.get("ok") and not p.get("reasoning_only") and p.get("probe_sec", 99) < 15
    ]
    print(f"\n벤치 대상 {len(ok)}개: {ok}", flush=True)

    results = []
    for m in ok:
        print(f"\n--- {m} ---", flush=True)
        r = bench(m)
        results.append(r)
        for t, v in r["tests"].items():
            if v.get("ok"):
                print(
                    f"  {t}: {v['elapsed_sec']}s tok={v['completion_tokens']} len={v['content_len']} | {v['preview'][:80]}",
                    flush=True,
                )
            else:
                print(f"  {t}: FAIL {v.get('error')}", flush=True)

    Path(__file__).parent.joinpath("nvidia_bench_extra.json").write_text(
        json.dumps({"probes": probes, "bench": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\n저장 완료", flush=True)
