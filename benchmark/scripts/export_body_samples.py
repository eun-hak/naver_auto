"""2000~3000자 본문 TOP 4 모델 — 전체 글 재생성 및 저장."""
from __future__ import annotations

import sys
from pathlib import Path

from _paths import ROOT, SAMPLES

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from body_2500_benchmark import MODELS, PROMPT, SYSTEM, bench_one

OUT_DIR = SAMPLES / "body_2500"

TOP4_IDS = [
    "gemini-3.1-flash-lite",
    "meta/llama-3.1-8b-instruct",
    "llama-3.1-8b-instant",
    "qwen/qwen3-next-80b-a3b-instruct",
]


def slug(model_id: str) -> str:
    return model_id.replace("/", "_").replace(".", "-")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    specs = [m for m in MODELS if m.id in TOP4_IDS]
    for spec in specs:
        print(f"Generating: {spec.label} ({spec.provider})...", flush=True)
        r = bench_one(spec)
        if not r.get("ok"):
            print(f"  FAIL: {r.get('error')}", flush=True)
            continue
        content = r["content"]
        name = slug(spec.id)
        path = OUT_DIR / f"{name}.md"
        meta = (
            f"<!-- provider: {spec.provider} | model: {spec.id} | "
            f"chars: {r['content_len']} | elapsed: {r['elapsed_sec']}s -->\n\n"
        )
        path.write_text(meta + content, encoding="utf-8")
        print(f"  saved {r['content_len']} chars -> {path.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
