"""NVIDIA MiniMax M2.7 API 테스트 스크립트."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

key = os.getenv("NVIDIA_API_KEY")
if not key:
    raise SystemExit("ERROR: NVIDIA_API_KEY not found")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=key,
)

tests = [
    {
        "name": "basic",
        "messages": [{"role": "user", "content": '한국어로 "안녕하세요"라고만 답해주세요.'}],
        "max_tokens": 512,
    },
    {
        "name": "blog_title",
        "messages": [
            {
                "role": "user",
                "content": (
                    '키워드 "제주도 맛집"으로 네이버 블로그 SEO 제목 3개를 '
                    'JSON 배열로만 출력하세요. 예: ["제목1", "제목2", "제목3"]'
                ),
            }
        ],
        "max_tokens": 2048,
    },
    {
        "name": "blog_body_short",
        "messages": [
            {
                "role": "user",
                "content": (
                    '키워드 "제주도 맛집"으로 네이버 블로그 본문 300자 분량을 작성하세요. '
                    "자연스러운 한국어, SEO 친화적."
                ),
            }
        ],
        "max_tokens": 4096,
    },
]

results = []
for t in tests:
    start = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model="minimaxai/minimax-m2.7",
            messages=t["messages"],
            temperature=1,
            top_p=0.95,
            max_tokens=t["max_tokens"],
            stream=False,
        )
        elapsed = time.perf_counter() - start
        choice = completion.choices[0]
        msg_obj = choice.message
        content = msg_obj.content or ""
        reasoning = getattr(msg_obj, "reasoning_content", None) or ""
        usage = completion.usage
        timing = (completion.model_dump().get("nvext") or {}).get("timing") or {}
        result = {
            "test": t["name"],
            "ok": True,
            "elapsed_sec": round(elapsed, 2),
            "finish_reason": choice.finish_reason,
            "prompt_tokens": usage.prompt_tokens if usage else None,
            "completion_tokens": usage.completion_tokens if usage else None,
            "total_tokens": usage.total_tokens if usage else None,
            "ttft_ms": timing.get("ttft_ms"),
            "total_ms": timing.get("total_time_ms"),
            "content_len": len(content),
            "reasoning_len": len(reasoning),
            "content_preview": content[:200].replace("\n", " "),
        }
        results.append(result)
        print(f"=== {t['name']} OK ({elapsed:.2f}s) ===")
        print(f"finish_reason: {choice.finish_reason}")
        if timing:
            print(f"ttft: {timing.get('ttft_ms')}ms, total: {timing.get('total_time_ms')}ms")
        print(f"content ({len(content)} chars): {content[:500]}")
        if reasoning and not content:
            print(f"reasoning only ({len(reasoning)} chars), tail: ...{reasoning[-200:]}")
        print()
    except Exception as e:
        elapsed = time.perf_counter() - start
        results.append(
            {"test": t["name"], "ok": False, "elapsed_sec": round(elapsed, 2), "error": str(e)}
        )
        print(f"=== {t['name']} FAIL ({elapsed:.2f}s) ===")
        print(str(e))
        print()

print("--- SUMMARY ---")
print(json.dumps(results, ensure_ascii=False, indent=2))

# 본문 생성은 reasoning 토큰 소비가 크므로 max_tokens=8192로 추가 테스트
print("\n=== blog_body_8192 ===")
start = time.perf_counter()
try:
    completion = client.chat.completions.create(
        model="minimaxai/minimax-m2.7",
        messages=[
            {
                "role": "user",
                "content": (
                    '키워드 "제주도 맛집"으로 네이버 블로그 본문 300자 분량을 작성하세요. '
                    "자연스러운 한국어, SEO 친화적."
                ),
            }
        ],
        temperature=1,
        top_p=0.95,
        max_tokens=8192,
        stream=False,
    )
    elapsed = time.perf_counter() - start
    choice = completion.choices[0]
    msg_obj = choice.message
    content = msg_obj.content or ""
    reasoning = getattr(msg_obj, "reasoning_content", None) or ""
    usage = completion.usage
    timing = (completion.model_dump().get("nvext") or {}).get("timing") or {}
    print(f"OK ({elapsed:.2f}s) finish={choice.finish_reason}")
    print(f"tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}")
    print(f"content_len={len(content)}, reasoning_len={len(reasoning)}")
    print(f"content:\n{content[:800]}")
except Exception as e:
    print(f"FAIL ({time.perf_counter() - start:.2f}s): {e}")
