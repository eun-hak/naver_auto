"""Imagen 4 이미지 생성 — 모델별 일일 한도 로테이션."""

from __future__ import annotations

import json
import os
from datetime import date
from io import BytesIO
from pathlib import Path

from google import genai
from google.genai import types
from PIL import Image

from naver_auto.image.cards import create_card_image
from naver_auto.paths import DATA_DIR

# Google AI Studio 표시명 ↔ Gemini API model code
IMAGEN_MODELS = [
    "imagen-4.0-generate-001",       # Imagen 4 Generate
    "imagen-4.0-ultra-generate-001",  # Imagen 4 Ultra Generate
    "imagen-4.0-fast-generate-001",  # Imagen 4 Fast Generate
]
IMAGEN_DISPLAY_NAMES = {
    "imagen-4.0-generate-001": "Imagen 4 Generate",
    "imagen-4.0-ultra-generate-001": "Imagen 4 Ultra Generate",
    "imagen-4.0-fast-generate-001": "Imagen 4 Fast Generate",
}
IMAGEN_LIMIT_PER_MODEL = int(os.getenv("IMAGEN_DAILY_LIMIT_PER_MODEL", "25"))
USAGE_FILE = DATA_DIR / "imagen_usage.json"


class ImagenQuotaError(Exception):
    """Imagen 모델 일일 한도 초과."""


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _load_usage() -> dict:
    today = date.today().isoformat()
    if USAGE_FILE.exists():
        try:
            data = json.loads(USAGE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if data.get("date") == today and isinstance(data.get("models"), dict):
            for model in IMAGEN_MODELS:
                data["models"].setdefault(model, 0)
            return data
    return {"date": today, "models": {model: 0 for model in IMAGEN_MODELS}}


def _save_usage(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with USAGE_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _is_quota_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("429", "quota", "resource_exhausted", "rate limit", "rate_limit")
    )


def _pick_model(usage: dict) -> str | None:
    for model in IMAGEN_MODELS:
        if int(usage["models"].get(model, 0)) < IMAGEN_LIMIT_PER_MODEL:
            return model
    return None


def _mark_model_exhausted(usage: dict, model: str) -> None:
    usage["models"][model] = IMAGEN_LIMIT_PER_MODEL
    _save_usage(usage)


def _increment_usage(usage: dict, model: str) -> None:
    usage["models"][model] = int(usage["models"].get(model, 0)) + 1
    _save_usage(usage)


def _save_jpeg(raw_bytes: bytes, output_path: Path, *, slot: int = 1) -> None:
    from naver_auto.image.postprocess import save_processed_jpeg

    img = Image.open(BytesIO(raw_bytes))
    save_processed_jpeg(img, output_path, source="gemini", slot=slot)


def _call_imagen(model: str, prompt: str) -> tuple[bytes, str]:
    """Imagen 4 generate_images 호출. (bytes, 사용 모델 ID) 반환."""
    client = _client()
    response = client.models.generate_images(
        model=model,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9",
        ),
    )
    images = response.generated_images or []
    if not images:
        raise RuntimeError(f"{IMAGEN_DISPLAY_NAMES.get(model, model)}: 응답에 이미지 없음")
    raw = images[0].image.image_bytes
    if not raw:
        raise RuntimeError(f"{IMAGEN_DISPLAY_NAMES.get(model, model)}: image_bytes 없음")
    return raw, model


def generate_gemini_image(
    output_path: Path,
    *,
    prompt: str,
    keyword: str,
    index: int,
) -> tuple[Path | None, str | None, str | None]:
    """Imagen 4로 이미지 생성. (경로, 에러, 사용 모델 ID) 반환."""
    if not gemini_configured():
        return None, "GEMINI_API_KEY 없음", None

    full_prompt = (
        f"Blog photo, 16:9, topic: {keyword}. {prompt}. "
        "Photorealistic, no text overlay, no watermark."
    )
    usage = _load_usage()
    last_err: str | None = None

    while True:
        model = _pick_model(usage)
        if not model:
            return None, last_err or "Imagen 4 일일 한도(75장) 소진", None

        label = IMAGEN_DISPLAY_NAMES.get(model, model)
        try:
            raw, used_model = _call_imagen(model, full_prompt)
            _save_jpeg(raw, output_path, slot=index + 1)
            _increment_usage(usage, used_model)
            return output_path, None, used_model
        except Exception as exc:
            last_err = f"{label} ({model}): {exc}"
            if _is_quota_error(exc):
                _mark_model_exhausted(usage, model)
                usage = _load_usage()
                continue
            return None, last_err, None


def generate_or_fallback(
    output_path: Path,
    *,
    keyword: str,
    section_hint: str,
    index: int,
) -> Path:
    prompt = f"{section_hint} related atmospheric photo"
    result, _err, _model = generate_gemini_image(
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
