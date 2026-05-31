"""Groq / Gemini / NVIDIA NIM 전체 모델 블로그 성능 벤치마크."""
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

OUT_JSON = ROOT / "scripts" / "full_model_benchmark_results.json"

PROMPTS = {
    "basic": {
        "text": '한국어로 "안녕하세요"라고만 답해주세요.',
        "max_tokens": 64,
        "temperature": 0.3,
    },
    "blog_title": {
        "text": (
            '키워드 "제주도 맛집"으로 네이버 블로그 SEO 제목 3개를 '
            'JSON 배열만 출력하세요. 예: ["제목1", "제목2", "제목3"]'
        ),
        "max_tokens": 400,
        "temperature": 0.7,
    },
    "blog_body_300": {
        "text": (
            '키워드 "제주도 맛집"으로 네이버 블로그 본문 300자 분량을 작성하세요. '
            "자연스러운 한국어, SEO 친화적. 마크다운 없이 본문만."
        ),
        "max_tokens": 800,
        "temperature": 0.7,
    },
    "blog_body_1500": {
        "text": (
            '키워드 "제주도 맛집"으로 네이버 블로그 본문을 작성하세요.\n'
            "- 분량: 1500~2000자 (공백 포함)\n"
            "- 톤: 존댓말 (~습니다)\n"
            "- H1 제목 1개 + ## 섹션 2개 + 마무리\n"
            "- 마크다운만 출력, 추론 과정 없이"
        ),
        "max_tokens": 2500,
        "temperature": 0.6,
    },
}


@dataclass
class ModelSpec:
    id: str
    provider: str
    label: str
    role: str = ""
    extra: dict = field(default_factory=dict)


MODELS: list[ModelSpec] = [
    # Groq (4)
    ModelSpec("llama-3.1-8b-instant", "groq", "Llama 3.1 8B Instant", "fast"),
    ModelSpec("qwen/qwen3-32b", "groq", "Qwen3 32B", "draft", {"reasoning_format": "hidden"}),
    ModelSpec("llama-3.3-70b-versatile", "groq", "Llama 3.3 70B Versatile", "quality"),
    ModelSpec("meta-llama/llama-4-scout-17b-16e-instruct", "groq", "Llama 4 Scout 17B", "scout"),
    # Gemini
    ModelSpec("gemini-2.5-flash-lite", "gemini", "Gemini 2.5 Flash Lite", "fast_alt"),
    ModelSpec("gemini-3.1-flash-lite", "gemini", "Gemini 3.1 Flash Lite", "fast"),
    ModelSpec("gemma-4-26b-a4b-it", "gemini", "Gemma 4 26B", "body"),
    ModelSpec("gemma-4-31b-it", "gemini", "Gemma 4 31B", "body_alt"),
    # NVIDIA NIM
    ModelSpec("meta/llama-4-maverick-17b-128e-instruct", "nvidia", "Llama 4 Maverick 17B", "fast"),
    ModelSpec("meta/llama-3.1-8b-instruct", "nvidia", "Llama 3.1 8B Instruct", "fast_alt"),
    ModelSpec("meta/llama-3.3-70b-instruct", "nvidia", "Llama 3.3 70B Instruct", "quality"),
    ModelSpec("google/gemma-4-31b-it", "nvidia", "Gemma 4 31B (NIM)", "body"),
    ModelSpec("qwen/qwen3-next-80b-a3b-instruct", "nvidia", "Qwen3 Next 80B", "draft"),
    ModelSpec("meta/llama-3.1-70b-instruct", "nvidia", "Llama 3.1 70B Instruct", "quality_alt"),
]


def _groq_client():
    from openai import OpenAI

    key = os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY")
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=120.0)


def _nvidia_client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("NVIDIA_API_KEY"),
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=180.0,
    )


def _call_groq(spec: ModelSpec, prompt: str, max_tokens: int, temperature: float) -> dict:
    kwargs = {
        "model": spec.id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if spec.extra.get("reasoning_format"):
        kwargs["extra_body"] = {"reasoning_format": spec.extra["reasoning_format"]}
    r = _groq_client().chat.completions.create(**kwargs)
    msg = r.choices[0].message
    content = (msg.content or "").strip()
    reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
    return {
        "content": content,
        "reasoning": reasoning,
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
        "prompt_tokens": r.usage.prompt_tokens if r.usage else None,
    }


def _call_nvidia(spec: ModelSpec, prompt: str, max_tokens: int, temperature: float) -> dict:
    r = _nvidia_client().chat.completions.create(
        model=spec.id,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        top_p=0.95,
        max_tokens=max_tokens,
    )
    msg = r.choices[0].message
    content = (msg.content or "").strip()
    reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
    timing = (r.model_dump().get("nvext") or {}).get("timing") or {}
    return {
        "content": content,
        "reasoning": reasoning,
        "finish": r.choices[0].finish_reason,
        "completion_tokens": r.usage.completion_tokens if r.usage else None,
        "prompt_tokens": r.usage.prompt_tokens if r.usage else None,
        "ttft_ms": timing.get("ttft_ms"),
        "total_ms": timing.get("total_time_ms"),
    }


def _call_gemini(spec: ModelSpec, prompt: str, max_tokens: int, temperature: float) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel(
        spec.id,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    r = model.generate_content(prompt)
    content = (r.text or "").strip()
    return {
        "content": content,
        "reasoning": "",
        "finish": "stop",
        "completion_tokens": None,
        "prompt_tokens": None,
    }


def call_model(spec: ModelSpec, test_name: str) -> dict:
    cfg = PROMPTS[test_name]
    start = time.perf_counter()
    try:
        if spec.provider == "groq":
            raw = _call_groq(spec, cfg["text"], cfg["max_tokens"], cfg["temperature"])
        elif spec.provider == "nvidia":
            raw = _call_nvidia(spec, cfg["text"], cfg["max_tokens"], cfg["temperature"])
        elif spec.provider == "gemini":
            raw = _call_gemini(spec, cfg["text"], cfg["max_tokens"], cfg["temperature"])
        else:
            raise ValueError(f"unknown provider: {spec.provider}")

        elapsed = time.perf_counter() - start
        content = raw["content"]
        reasoning = raw["reasoning"]
        return {
            "ok": True,
            "elapsed_sec": round(elapsed, 2),
            "finish": raw["finish"],
            "completion_tokens": raw["completion_tokens"],
            "prompt_tokens": raw["prompt_tokens"],
            "content_len": len(content),
            "reasoning_len": len(reasoning),
            "reasoning_only": bool(reasoning) and not content,
            "preview": content[:200],
            "ttft_ms": raw.get("ttft_ms"),
            "total_ms": raw.get("total_ms"),
        }
    except Exception as e:
        return {
            "ok": False,
            "elapsed_sec": round(time.perf_counter() - start, 2),
            "error": str(e)[:200],
        }


def korean_ratio(text: str) -> float:
    if not text:
        return 0.0
    hangul = len(re.findall(r"[가-힣]", text))
    return hangul / max(len(text.replace(" ", "")), 1)


def json_title_score(text: str) -> float:
    if not text:
        return 0.0
    clean = re.sub(r"```(?:json)?\s*", "", text)
    clean = clean.replace("```", "").strip()
    m = re.search(r"\[[\s\S]*?\]", clean)
    if not m:
        return 0.0
    try:
        arr = json.loads(m.group())
        if isinstance(arr, list) and len(arr) >= 2:
            return min(10.0, 5.0 + len(arr))
    except json.JSONDecodeError:
        pass
    return 2.0 if "[" in text else 0.0


def body_score(test: str, result: dict) -> float:
    if not result.get("ok"):
        return 0.0
    content = result.get("preview", "")
    cl = result.get("content_len", 0)
    s = 0.0
    s += min(10, korean_ratio(content) * 12)
    if test == "blog_body_300":
        if 200 <= cl <= 500:
            s += 10
        elif 150 <= cl <= 700:
            s += 6
        elif cl > 0:
            s += 2
    elif test == "blog_body_1500":
        if 1200 <= cl <= 2500:
            s += 10
        elif 800 <= cl <= 3000:
            s += 6
        elif cl > 300:
            s += 3
    if result.get("reasoning_only"):
        s = 0.0
    if re.search(r"[a-zA-Z]{20,}", content[:300]) and korean_ratio(content) < 0.3:
        s *= 0.3
    return s


def score_model(results: dict) -> dict:
    tests = results.get("tests", {})
    scores = {}
    total = 0.0
    count = 0
    for name, t in tests.items():
        if not t.get("ok"):
            scores[name] = 0.0
            continue
        if name == "basic":
            sc = 10.0 if t.get("content_len", 0) > 0 and not t.get("reasoning_only") else 0.0
        elif name == "blog_title":
            sc = json_title_score(t.get("preview", ""))
            sc += min(5, max(0, 5 - t.get("elapsed_sec", 5)))
            if korean_ratio(t.get("preview", "")) < 0.2:
                sc *= 0.5
        else:
            sc = body_score(name, t)
            sc += min(3, max(0, 3 - t.get("elapsed_sec", 3) / 10))
        scores[name] = round(sc, 1)
        total += sc
        count += 1
    return {
        "by_test": scores,
        "total": round(total, 1),
        "avg": round(total / count, 1) if count else 0.0,
    }


def run_benchmark() -> dict:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompts": {k: v["text"][:80] + "..." for k, v in PROMPTS.items()},
        "models": [],
    }

    for i, spec in enumerate(MODELS, 1):
        print(f"\n[{i}/{len(MODELS)}] {spec.provider}/{spec.id}", flush=True)
        entry = {
            "id": spec.id,
            "provider": spec.provider,
            "label": spec.label,
            "role": spec.role,
            "tests": {},
        }
        for test_name in PROMPTS:
            print(f"  {test_name}...", end=" ", flush=True)
            r = call_model(spec, test_name)
            entry["tests"][test_name] = r
            if r.get("ok"):
                print(
                    f"OK {r['elapsed_sec']}s len={r.get('content_len')} tok={r.get('completion_tokens')}",
                    flush=True,
                )
            else:
                print(f"FAIL {r.get('error', '')[:60]}", flush=True)
            time.sleep(0.5)
        entry["score"] = score_model(entry)
        report["models"].append(entry)

    ranked = sorted(report["models"], key=lambda m: m["score"]["total"], reverse=True)
    report["ranking"] = [
        {
            "rank": i + 1,
            "id": m["id"],
            "provider": m["provider"],
            "label": m["label"],
            "total_score": m["score"]["total"],
            "avg_score": m["score"]["avg"],
        }
        for i, m in enumerate(ranked)
    ]
    return report


if __name__ == "__main__":
    data = run_benchmark()
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT_JSON}", flush=True)
    print("\n=== TOP 10 ===", flush=True)
    for row in data["ranking"][:10]:
        print(f"  {row['rank']}. [{row['provider']}] {row['label']} — {row['total_score']}점", flush=True)
