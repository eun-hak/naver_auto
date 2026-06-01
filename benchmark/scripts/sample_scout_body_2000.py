"""Groq Llama 4 Scout — 1500~2500자 본문 샘플."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from _paths import ROOT, SAMPLES

# project root via _paths
load_dotenv(ROOT / ".env")
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
- 분량: {MIN_CHARS}~{MAX_CHARS}자 (공백 포함) — 반드시 {MIN_CHARS}자 이상 써줘
- 시작: H1 바로 아래 2~3문단을 일반 단락으로 자연스럽게 쓸 것
- 본문: ## 섹션 2~3개 → 체크리스트 → FAQ 1~2개 → 마무리 질문 + #해시태그 3개+
- 금지: "## 도입" 같은 메타 섹션, 반복 문장, 가짜 가게명(「제주 OO점」 형태)
- 톤: 존댓말 (~습니다)
- 마크다운만 출력
"""

MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
OUT = SAMPLES / "body_2000" / "meta-llama_llama-4-scout-17b.md"

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY") or os.getenv("GROK_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
    timeout=120.0,
)

start = time.perf_counter()
r = client.chat.completions.create(
    model=MODEL,
    messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": PROMPT}],
    temperature=0.6,
    max_tokens=4096,
)
elapsed = time.perf_counter() - start
content = (r.choices[0].message.content or "").strip()
cl = len(content)

OUT.parent.mkdir(parents=True, exist_ok=True)
meta = (
    f"<!-- provider: groq | model: {MODEL} | chars: {cl} | "
    f"target: {MIN_CHARS}~{MAX_CHARS} | elapsed: {elapsed:.2f}s -->\n\n"
)
OUT.write_text(meta + content, encoding="utf-8")

print(f"chars={cl} target={'OK' if MIN_CHARS <= cl <= MAX_CHARS else 'MISS'} elapsed={elapsed:.2f}s")
print(f"saved: {OUT.relative_to(ROOT)}")
print("---")
print(content)
