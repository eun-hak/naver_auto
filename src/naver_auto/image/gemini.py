"""Imagen 4 이미지 생성 — 모델별 일일 한도 로테이션."""

from __future__ import annotations

import base64
import json
import os
from datetime import date
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from naver_auto.image.cards import create_card_image
from naver_auto.paths import DATA_DIR

IMAGEN_MODELS = [
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
]
IMAGEN_LIMIT_PER_MODEL = int(os.getenv("IMAGEN_DAILY_LIMIT_PER_MODEL", "25"))
USAGE_FILE = DATA_DIR / "imagen_usage.json"
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class ImagenQuotaError(Exception):
    """Imagen 모델 한도 초과."""


def gemini_configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


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


def _is_quota_response(status_code: int, body: str) -> bool:
    if status_code == 429:
        return True
    lower = body.lower()
    return any(
        token in lower
        for token in ("quota", "resource_exhausted", "rate limit", "rate_limit")
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


def _call_imagen(model: str, prompt: str, api_key: str) -> bytes:
    url = f"{API_BASE}/{model}:predict"
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "16:9",
        },
    }
    response = httpx.post(
        url,
        params={"key": api_key},
        json=payload,
        timeout=120.0,
    )
    body = response.text
    if _is_quota_response(response.status_code, body):
        raise ImagenQuotaError(body[:300])
    response.raise_for_status()
    data = response.json()
    predictions = data.get("predictions") or []
    if not predictions:
        raise RuntimeError("Imagen 응답에 이미지 없음")
    b64 = predictions[0].get("bytesBase64Encoded")
    if not b64:
        raise RuntimeError("Imagen 응답에 bytesBase64Encoded 없음")
    return base64.b64decode(b64)


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

    full_prompt = (
        f"Blog photo, 16:9, topic: {keyword}. {prompt}. "
        "Photorealistic, no text overlay, no watermark."
    )
    usage = _load_usage()

    while True:
        model = _pick_model(usage)
        if not model:
            return None
        try:
            raw = _call_imagen(model, full_prompt, api_key)
            _save_jpeg(raw, output_path, slot=index + 1)
            _increment_usage(usage, model)
            return output_path
        except ImagenQuotaError:
            _mark_model_exhausted(usage, model)
            usage = _load_usage()
            continue
        except Exception:
            return None


def generate_or_fallback(
    output_path: Path,
    *,
    keyword: str,
    section_hint: str,
    index: int,
) -> Path:
    prompt = f"{section_hint} related atmospheric photo"
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
