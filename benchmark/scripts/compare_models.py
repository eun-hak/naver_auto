"""MiniMax M2.7 vs 기존 모델 비교 벤치마크."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from _paths import ROOT

load_dotenv(ROOT / ".env")
sys.stdout.reconfigure(encoding="utf-8")

PROMPTS = {
    "basic": '한국어로 "안녕하세요"라고만 답해주세요.',
    "blog_title": (
        '키워드 "제주도 맛집"으로 네이버 블로그 SEO 제목 3개를 '
        'JSON 배열로만 출력하세요. 예: ["제목1", "제목2", "제목3"]'
    ),
    "blog_body": (
        '키워드 "제주도 맛집"으로 네이버 블로그 본문 300자 분량을 작성하세요. '
        "자연스러운 한국어, SEO 친화적."
    ),
}


def bench_nvidia(name: str, prompt: str, max_tokens: int) -> dict:
    from openai import OpenAI

    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY"),
    )
    start = time.perf_counter()
    r = client.chat.completions.create(
        model="minimaxai/minimax-m2.7",
        messages=[{"role": "user", "content": prompt}],
        temperature=1,
        top_p=0.95,
        max_tokens=max_tokens,
    )
    elapsed = time.perf_counter() - start
    msg = r.choices[0].message
    content = (msg.content or "").strip()
    reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
    return {
        "model": "minimax-m2.7 (NVIDIA)",
        "test": name,
        "elapsed_sec": round(elapsed, 2),
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
        "content_len": len(content),
        "reasoning_len": len(reasoning),
        "preview": content[:120],
    }


def bench_groq(name: str, prompt: str, model: str, max_tokens: int = 1024) -> dict:
    from openai import OpenAI

    key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    start = time.perf_counter()
    r = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=max_tokens,
    )
    elapsed = time.perf_counter() - start
    content = (r.choices[0].message.content or "").strip()
    return {
        "model": model,
        "test": name,
        "elapsed_sec": round(elapsed, 2),
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
        "content_len": len(content),
        "reasoning_len": 0,
        "preview": content[:120],
    }


def bench_gemini(name: str, prompt: str, model: str) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    m = genai.GenerativeModel(model)
    start = time.perf_counter()
    r = m.generate_content(prompt)
    elapsed = time.perf_counter() - start
    content = (r.text or "").strip()
    return {
        "model": model,
        "test": name,
        "elapsed_sec": round(elapsed, 2),
        "finish": "stop",
        "completion_tokens": None,
        "content_len": len(content),
        "reasoning_len": 0,
        "preview": content[:120],
    }


rows = []
for test, prompt in PROMPTS.items():
    max_tok = 512 if test == "basic" else (2048 if test == "blog_title" else 8192)
    if test != "blog_body":
        rows.append(bench_nvidia(test, prompt, max_tok))
    rows.append(bench_groq(
        test,
        prompt,
        "llama-3.1-8b-instant" if test != "blog_body" else "qwen/qwen3-32b",
        512 if test == "basic" else (1024 if test == "blog_title" else 2048),
    ))
    rows.append(bench_gemini(
        test,
        prompt,
        "gemini-3.1-flash-lite" if test != "blog_body" else "gemma-4-26b-a4b-it",
    ))

# blog_body NVIDIA 결과는 별도 장시간 테스트에서 확인 (211s, 7452 tok)
rows.append({
    "model": "minimax-m2.7 (NVIDIA)",
    "test": "blog_body",
    "elapsed_sec": 211.64,
    "finish": "stop",
    "completion_tokens": 7452,
    "content_len": 304,
    "reasoning_len": 19054,
    "preview": "(별도 8192 max_tokens 테스트)",
})

print(f"{'model':<35} {'test':<12} {'sec':>6} {'tok':>6} {'chars':>6} preview")
print("-" * 110)
for r in rows:
    print(
        f"{r['model']:<35} {r['test']:<12} {r['elapsed_sec']:>6.1f} "
        f"{r['completion_tokens'] or '-':>6} {r['content_len']:>6} {r['preview'][:60]}"
    )
