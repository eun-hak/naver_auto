"""NVIDIA NIM 무료 모델 탐색 + 블로그 글쓰기 적합 모델 벤치마크."""
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

BASE = "https://integrate.api.nvidia.com/v1"
key = os.getenv("NVIDIA_API_KEY")
if not key:
    raise SystemExit("NVIDIA_API_KEY missing")

client = OpenAI(base_url=BASE, api_key=key)

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

# 블로그 글쓰기에 적합할 것으로 선정한 후보 (reasoning-only 제외, 한국어/일반 LLM 위주)
CANDIDATES = [
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.3-70b-instruct",
    "mistralai/mistral-nemo-12b-instruct",
    "mistralai/mixtral-8x7b-instruct-v0.1",
    "nvidia/nemotron-4-340b-instruct",
    "qwen/qwen2.5-72b-instruct",
    "qwen/qwen2.5-7b-instruct",
    "google/gemma-3-27b-it",
    "microsoft/phi-3-mini-128k-instruct",
    "deepseek-ai/deepseek-v3.1",
    "moonshotai/kimi-k2-instruct",
]


def list_models() -> list[str]:
    models = client.models.list()
    return sorted(m.id for m in models.data)


def probe_model(model: str) -> dict:
    """모델 존재/응답 여부 빠른 확인."""
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPTS["basic"]}],
            temperature=0.7,
            max_tokens=64,
            timeout=60,
        )
        msg = r.choices[0].message
        content = (msg.content or "").strip()
        reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
        return {
            "model": model,
            "ok": True,
            "content": content[:80],
            "has_reasoning": bool(reasoning),
            "finish": r.choices[0].finish_reason,
        }
    except Exception as e:
        return {"model": model, "ok": False, "error": str(e)[:120]}


def bench_model(model: str) -> dict:
    results = {"model": model, "tests": {}}
    for name, prompt in PROMPTS.items():
        max_tokens = 128 if name == "basic" else (512 if name == "blog_title" else 1024)
        start = time.perf_counter()
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7 if name != "basic" else 0.3,
                max_tokens=max_tokens,
                timeout=120,
            )
            elapsed = time.perf_counter() - start
            msg = r.choices[0].message
            content = (msg.content or "").strip()
            reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
            usage = r.usage
            results["tests"][name] = {
                "ok": True,
                "elapsed_sec": round(elapsed, 2),
                "finish": r.choices[0].finish_reason,
                "completion_tokens": usage.completion_tokens if usage else None,
                "content_len": len(content),
                "has_reasoning": bool(reasoning),
                "preview": content[:100],
            }
        except Exception as e:
            results["tests"][name] = {
                "ok": False,
                "elapsed_sec": round(time.perf_counter() - start, 2),
                "error": str(e)[:150],
            }
    return results


def score_model(r: dict) -> float:
    """블로그 적합도 간단 점수."""
    tests = r.get("tests", {})
    s = 0.0
    for name in ("basic", "blog_title", "blog_body"):
        t = tests.get(name, {})
        if not t.get("ok"):
            return -1
        if t.get("has_reasoning"):
            s -= 5  # reasoning 모델 감점
        if name == "blog_body" and t.get("content_len", 0) < 150:
            s -= 10
        if name == "blog_title" and "[" not in t.get("preview", ""):
            s -= 3
        s += max(0, 20 - t.get("elapsed_sec", 20))  # 빠를수록 가점
        if name == "blog_body":
            cl = t.get("content_len", 0)
            if 200 <= cl <= 600:
                s += 10
            elif cl >= 150:
                s += 5
    return s


if __name__ == "__main__":
    print("=== NVIDIA NIM 모델 목록 조회 ===")
    all_models = list_models()
    print(f"총 {len(all_models)}개 모델")
    out_dir = Path(__file__).resolve().parent
    (out_dir / "nvidia_models.json").write_text(
        json.dumps(all_models, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n=== 후보 모델 프로브 ===")
    available = []
    for m in CANDIDATES:
        p = probe_model(m)
        status = "OK" if p.get("ok") else "FAIL"
        extra = p.get("content", p.get("error", ""))[:60]
        print(f"  [{status}] {m}: {extra}")
        if p.get("ok") and not p.get("has_reasoning"):
            available.append(m)

    # 프로브 성공 + reasoning 없는 모델 우선, 없으면 ok 모델 전체
    to_bench = available or [m for m in CANDIDATES if probe_model(m).get("ok")]
    # 중복 제거, 최대 6개
    seen = set()
    selected = []
    for m in to_bench:
        if m not in seen:
            seen.add(m)
            selected.append(m)
        if len(selected) >= 6:
            break

    print(f"\n=== 선정 {len(selected)}개 모델 풀 벤치마크 ===")
    bench_results = []
    for m in selected:
        print(f"\n--- {m} ---")
        r = bench_model(m)
        bench_results.append(r)
        for tname, t in r["tests"].items():
            if t.get("ok"):
                print(
                    f"  {tname}: {t['elapsed_sec']}s, "
                    f"tok={t.get('completion_tokens')}, "
                    f"len={t['content_len']}, "
                    f"preview={t['preview'][:60]}"
                )
            else:
                print(f"  {tname}: FAIL - {t.get('error')}")

    ranked = sorted(
        [(score_model(r), r) for r in bench_results],
        key=lambda x: x[0],
        reverse=True,
    )

    print("\n=== 블로그 적합도 순위 ===")
    for sc, r in ranked:
        print(f"  score={sc:.1f}  {r['model']}")

    (out_dir / "nvidia_bench_results.json").write_text(
        json.dumps(bench_results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n결과 저장: scripts/nvidia_bench_results.json")
