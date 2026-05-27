"""Gemini 이미지 생성 (Phase 2/3)."""

from __future__ import annotations

import os
from pathlib import Path

from naver_auto.image.cards import create_card_image


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def generate_gemini_image(
    output_path: Path,
    *,
    prompt: str,
    keyword: str,
    index: int,
) -> Path | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash-preview-image-generation")
        response = model.generate_content(
            f"블로그용 16:9 이미지. 주제: {keyword}. {prompt}. 텍스트 없이.",
            generation_config={"response_modalities": ["IMAGE", "TEXT"]},
        )
        for part in response.candidates[0].content.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with output_path.open("wb") as f:
                    f.write(part.inline_data.data)
                return output_path
    except Exception:
        return None

    return None


def generate_or_fallback(
    output_path: Path,
    *,
    keyword: str,
    section_hint: str,
    index: int,
) -> Path:
    prompt = f"{section_hint} 관련 분위기 있는 일러스트"
    result = generate_gemini_image(
        output_path,
        prompt=prompt,
        keyword=keyword,
        index=index,
    )
    if result:
        return result
    return create_card_image(
        output_path,
        title=keyword,
        subtitle=section_hint,
        index=index,
    )
