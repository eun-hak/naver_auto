#!/usr/bin/env python3
"""4개 Gemini 모델 본문 품질 비교 테스트.

예시:
  python scripts/compare_models.py
  python scripts/compare_models.py --keyword "에어팟 프로 3" \\
    --title "[솔직후기] 에어팟 프로 3 한 달 써본 리얼 장단점"
  python scripts/compare_models.py --keyword "제주도 맛집" --brief "흑돼지·고기국수 위주"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import google.generativeai as genai

from naver_auto.content.validator import quality_check

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

DEFAULT_KEYWORD = "탕수육"
DEFAULT_TITLE = "[강화도] 탕수육 맛집 추천: 순무탕수육 꼭 드세요! (내돈내산 후기)"
DEFAULT_BRIEF = (
    "탕수육 맛집 후기·지역별 추천·메뉴 조합 중심. "
    "강화도 금문도 순무탕수육 등 실제 맛집 정보 활용. 존댓말 SEO 글."
)
DEFAULT_REF = "- 묵호 거동 탕수육 후기\n- 강화도 금문도 순무탕수육 25,000원"

SYSTEM = "한국어 SEO 블로그 작가. 자연스러운 존댓말. 최종 글만."


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w가-힣]+", "_", text.strip(), flags=re.UNICODE)
    return slug.strip("_")[:40] or "run"


def build_prompt(*, keyword: str, title: str, brief: str, reference: str) -> str:
    return f"""다음 SEO 블로그 글을 마크다운으로 작성해.

- 제목(H1): {title}
- 핵심 키워드: {keyword}
- 분량: 1500~2500자
- 톤: **전체 존댓말** (~습니다, ~입니다)
- 구조: H1 → 도입 2~3문단 → ## 섹션 2~3개 → 체크리스트 → FAQ 1~2개 → 마무리 질문 + #해시태그 3개+
- 금지: "## 도입" 같은 메타 섹션 제목, 반말, 추측·과장

[조사 브리프]
{brief}

[참고 자료]
{reference}

마크다운만 출력.
"""


def call_model(model_name: str, prompt: str) -> dict:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 필요")
    genai.configure(api_key=key)
    model = genai.GenerativeModel(model_name, system_instruction=SYSTEM)
    t0 = time.time()
    try:
        resp = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(temperature=0.6),
        )
        text = (resp.text or "").strip()
        err = None
    except Exception as exc:
        text = ""
        err = str(exc)
    elapsed = round(time.time() - t0, 1)

    seo_cfg = {"body": {"min_chars": 1500, "max_chars": 3500}, "image_placeholder_count": 6}
    errors = quality_check(text, seo_cfg) if text else ["생성 실패"]

    formal = len(re.findall(r"(?:습니다|입니다|세요|더군요|드릴게요|해요)", text))
    sections = len(re.findall(r"^## ", text, re.M))
    hashtags = len(re.findall(r"#\w", text))

    return {
        "model": model_name,
        "error": err,
        "elapsed_sec": elapsed,
        "char_count": len(text),
        "formal_count": formal,
        "sections": sections,
        "hashtags": hashtags,
        "quality_errors": errors,
        "intro_preview": "\n".join(text.splitlines()[:8])[:400],
        "body": text,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gemini 모델별 본문 품질 비교")
    parser.add_argument(
        "--keyword", "-k",
        default=DEFAULT_KEYWORD,
        help=f"핵심 키워드 (기본: {DEFAULT_KEYWORD})",
    )
    parser.add_argument(
        "--title", "-t",
        default=None,
        help="SEO 제목(H1). 미지정 시 키워드 기반 기본 제목 사용",
    )
    parser.add_argument(
        "--brief", "-b",
        default=None,
        help="조사 브리프 (미지정 시 키워드 기반 기본값)",
    )
    parser.add_argument(
        "--reference", "-r",
        default=None,
        help="참고 자료 (줄바꿈은 \\n으로 전달)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="결과 저장 폴더 (기본: debug/model_compare/<키워드슬러그>)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keyword = args.keyword.strip()
    title = (args.title or f"{keyword} 완벽 가이드: 꼭 알아야 할 정보 총정리").strip()
    if keyword == DEFAULT_KEYWORD and args.title is None:
        title = DEFAULT_TITLE
    brief = (args.brief or f"{keyword} 관련 실용 정보·후기·추천 중심. 존댓말 SEO 글.").strip()
    if keyword == DEFAULT_KEYWORD and args.brief is None:
        brief = DEFAULT_BRIEF
    reference = (args.reference or f"- {keyword} 관련 검색 상위 글 요약\n- 실제 경험 기반 정보").replace("\\n", "\n")
    if keyword == DEFAULT_KEYWORD and args.reference is None:
        reference = DEFAULT_REF

    prompt = build_prompt(keyword=keyword, title=title, brief=brief, reference=reference)
    out_dir = Path(args.output_dir) if args.output_dir else ROOT / "debug" / "model_compare" / slugify(keyword)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"키워드: {keyword}")
    print(f"제목: {title}")
    print(f"저장: {out_dir}\n")

    results = []
    bodies: dict[str, str] = {}

    for name in MODELS:
        print(f"Testing {name}…", flush=True)
        result = call_model(name, prompt)
        summary_item = {k: v for k, v in result.items() if k != "body"}
        results.append(summary_item)
        if not result.get("error") and result.get("body"):
            bodies[name] = result["body"]
        time.sleep(2)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary_path = out_dir / f"summary_{ts}.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "keyword": keyword,
                "title": title,
                "brief": brief,
                "reference": reference,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    meta_by_model = {r["model"]: r for r in results}
    for name, text in bodies.items():
        safe = name.replace(".", "_")
        meta = meta_by_model.get(name, {})
        header = (
            f"<!-- model: {name} | chars: {meta.get('char_count', '?')} | "
            f"elapsed: {meta.get('elapsed_sec', '?')}s | "
            f"formal: {meta.get('formal_count', '?')} | "
            f"sections: {meta.get('sections', '?')} -->\n\n"
        )
        (out_dir / f"{safe}.md").write_text(header + text + "\n", encoding="utf-8")

    print("\n=== COMPARE SUMMARY ===")
    for r in results:
        status = "OK" if not r.get("error") else f"ERR: {r['error'][:60]}"
        q = len(r.get("quality_errors", []))
        print(
            f"{r['model']:<28} {r['elapsed_sec']:>5}s  {r['char_count']:>5}자  "
            f"존댓말{r['formal_count']:>3}  섹션{r['sections']}  경고{q}  {status}"
        )
    print(f"\nSaved: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
