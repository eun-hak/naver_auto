"""Groq Scout vs NIM 5종 빠른 비교 (실패/타임아웃 즉시 스킵)."""
from __future__ import annotations

import concurrent.futures
import os
import re
import sys
import time

from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".env.local")
sys.stdout.reconfigure(encoding="utf-8")

MIN, MAX = 1500, 2500
MAX_TOKENS = 2048
SYSTEM = (
    "너는 네이버 블로그에 글을 쓰는 한국어 작가다. "
    "H1 다음 자연스러운 도입. 반말·영어 혼입 금지. 최종 글만."
)
PROMPT = """재택근무 집중법 SEO 블로그 마크다운 작성.
H1: 재택근무 집중 잘하는 방법 | WFH 생산성 7가지
분량 1500~2500자, 존댓말, 제가/저는 경험 1~2곳, ## 2~3개, 해시태그."""

# (provider, model_id, label, hard_timeout_sec)
MODELS = [
    ("groq", "meta-llama/llama-4-scout-17b-16e-instruct", "Groq Scout 17B ★", 30),
    ("nvidia", "meta/llama-4-maverick-17b-128e-instruct", "NIM Maverick 17B", 45),
    ("nvidia", "stepfun-ai/step-3.7-flash", "NIM Step 3.7 Flash", 45),
    ("nvidia", "abacusai/dracarys-llama-3.1-70b-instruct", "NIM Dracarys 70B", 25),
    ("nvidia", "z-ai/glm-5.1", "NIM GLM 5.1", 25),
    ("nvidia", "minimaxai/minimax-m2.7", "NIM MiniMax M2.7", 20),
]


def _call(provider: str, model_id: str, http_timeout: float) -> dict:
    from openai import OpenAI

    if provider == "groq":
        client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
            timeout=http_timeout,
        )
        extra: dict = {}
    else:
        client = OpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=http_timeout,
        )
        extra = {"top_p": 0.95}

    r = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": PROMPT},
        ],
        temperature=0.6,
        max_tokens=MAX_TOKENS,
        **extra,
    )
    msg = r.choices[0].message
    txt = (msg.content or "").strip()
    if not txt and (getattr(msg, "reasoning_content", None) or "").strip():
        raise RuntimeError("reasoning_only")
    cl = len(txt)
    ko = len(re.findall(r"[가-힣]", txt)) / max(len(txt.replace(" ", "")), 1)
    return {
        "chars": cl,
        "in_target": MIN <= cl <= MAX,
        "ko": round(ko, 2),
        "tok": r.usage.completion_tokens if r.usage else None,
    }


def run_one(provider: str, model_id: str, hard_timeout: float) -> dict:
    t0 = time.perf_counter()
    http_timeout = min(hard_timeout, hard_timeout - 1) or hard_timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_call, provider, model_id, http_timeout)
        try:
            data = fut.result(timeout=hard_timeout)
        except concurrent.futures.TimeoutError as e:
            raise RuntimeError(f"timeout {hard_timeout}s") from e
    data["elapsed"] = round(time.perf_counter() - t0, 2)
    return data


def similarity(row: dict, baseline: dict) -> float:
    if not row.get("ok"):
        return 0.0
    bt, bl = baseline["elapsed"], baseline["chars"]
    sp = max(0, 1 - abs(row["elapsed"] - bt) / max(bt, 1))
    ln = max(0, 1 - abs(row["chars"] - bl) / max(bl, 200))
    tgt = 1.0 if row["in_target"] else 0.5 if 1300 <= row["chars"] <= 2800 else 0.0
    return round((sp * 0.4 + ln * 0.35 + tgt * 0.25) * 100, 1)


def main() -> None:
    rows: list[dict] = []
    baseline: dict | None = None

    for provider, model_id, label, hard_timeout in MODELS:
        print(f"[{label}] (max {hard_timeout}s) ...", flush=True)
        row: dict = {"label": label, "provider": provider, "id": model_id}
        t0 = time.perf_counter()
        try:
            data = run_one(provider, model_id, hard_timeout)
            row.update(data, ok=True)
            if "Scout" in label:
                baseline = row
            mark = "OK" if row["in_target"] else "MISS"
            print(
                f"  {row['elapsed']}s | {row['chars']}자 {mark} | ko={row['ko']:.0%}",
                flush=True,
            )
        except Exception as e:
            el = round(time.perf_counter() - t0, 2)
            err = str(e).split("\n")[0][:100]
            row.update(ok=False, error=err, elapsed=el, chars=0, in_target=False)
            print(f"  SKIP {el}s | {err}", flush=True)
        rows.append(row)

    if baseline is None:
        baseline = next((r for r in rows if r.get("ok")), {"elapsed": 4.0, "chars": 1400})

    for r in rows:
        r["similarity"] = similarity(r, baseline)

    rows.sort(key=lambda x: (-x["similarity"], x.get("elapsed", 999)))

    print("\n=== Scout 유사도 TOP ===", flush=True)
    for i, r in enumerate(rows, 1):
        if r.get("ok"):
            mark = "OK" if r["in_target"] else "MISS"
            print(
                f"{i}. {r['label']:<24} sim={r['similarity']:5.1f}% | "
                f"{r['elapsed']:5.1f}s | {r['chars']:4}자 {mark}",
                flush=True,
            )
        else:
            print(f"{i}. {r['label']:<24} SKIP ({r.get('elapsed', 0)}s) {r.get('error', '')}", flush=True)


if __name__ == "__main__":
    main()
