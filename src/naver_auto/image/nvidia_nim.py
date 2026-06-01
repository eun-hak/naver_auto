"""NVIDIA NIM hosted image generation — FLUX.1-schnell (ai.api.nvidia.com)."""

from __future__ import annotations

import base64
import os
import random
import re
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

NVIDIA_GENAI_BASE = "https://ai.api.nvidia.com/v1/genai"
DEFAULT_MODEL = "black-forest-labs/flux.1-schnell"
DEFAULT_LABEL = "FLUX.1-schnell"
# FLUX 응답이 60~90초 걸리는 경우가 있어 read 타임아웃 여유 확보
FLUX_TIMEOUT = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=30.0)

# NVIDIA FLUX content filter에 자주 걸리는 표현
_SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (r"donald\s*trump|트럼프|trump", "unidentified diplomat silhouette"),
    (r"iranian\s*military|war\s*room|군사|군함\s*공격|missile|weapon|폭격|공격", "maritime patrol"),
    (r"war\s*situation|전쟁\s*상황|전쟁|war\b|conflict\s*zone", "geopolitical tension"),
    (r"burning|화재|폭발|explosion|blood|violence", "dramatic sky"),
    (r"blockade|봉쇄|invasion|침공", "shipping delay"),
]


def nvidia_configured() -> bool:
    return bool(os.getenv("NVIDIA_API_KEY"))


def _model_path() -> str:
    from naver_auto.paths import load_yaml

    cfg = load_yaml("publish.yaml")
    return str(cfg.get("nvidia_image_model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _headers() -> dict[str, str]:
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise RuntimeError("NVIDIA_API_KEY 환경변수가 필요합니다.")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _save_jpeg(raw_bytes: bytes, output_path: Path, *, slot: int = 1) -> None:
    from naver_auto.image.postprocess import save_processed_jpeg

    img = Image.open(BytesIO(raw_bytes))
    save_processed_jpeg(img, output_path, source="nvidia", slot=slot)


def sanitize_flux_prompt(prompt: str, *, keyword: str) -> str:
    """콘텐츠 필터 회피용 — 실존 인물·전쟁·폭력 표현을 상징적 장면으로 완화."""
    text = prompt
    for pattern, repl in _SENSITIVE_PATTERNS:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ,.")
    return (
        f"Safe editorial photo about {keyword}. "
        "Symbolic scene: world map, civic gathering silhouette, city street at dusk, newsroom atmosphere. "
        "No recognizable public figures, no violence, no weapons, no text, no logos. "
        f"{text[:240]}"
    )


def _call_flux(
    *,
    model_path: str,
    full_prompt: str,
    seed: int,
) -> tuple[bytes | None, str | None]:
    url = f"{NVIDIA_GENAI_BASE}/{model_path}"
    response = httpx.post(
        url,
        headers=_headers(),
        json={
            "prompt": full_prompt,
            "width": 1344,
            "height": 768,
            "steps": 4,
            "seed": seed,
        },
        timeout=FLUX_TIMEOUT,
    )
    if response.status_code != 200:
        return None, f"HTTP {response.status_code} {response.text[:200]}"

    data = response.json()
    artifacts = data.get("artifacts") or []
    if not artifacts:
        return None, "artifacts 없음"

    artifact = artifacts[0]
    finish = artifact.get("finishReason")
    if finish not in (None, "SUCCESS"):
        if finish == "CONTENT_FILTERED":
            return None, "CONTENT_FILTERED"
        return None, f"finishReason={finish}"

    b64 = artifact.get("base64")
    if not b64:
        return None, "base64 없음"
    return base64.b64decode(b64), None


def generate_nvidia_image(
    output_path: Path,
    *,
    prompt: str,
    keyword: str,
    slot: int,
    model_path: str | None = None,
    seed: int | None = None,
) -> tuple[Path | None, str | None, str | None]:
    """FLUX.1-schnell로 이미지 생성. (경로, 에러, model_path) 반환."""
    if not nvidia_configured():
        return None, "NVIDIA_API_KEY 없음", None

    model_path = model_path or _model_path()
    label = DEFAULT_LABEL if "flux.1-schnell" in model_path else model_path.split("/")[-1]

    if seed is None:
        seed = random.randint(0, 2_147_483_647)

    attempts = [
        (
            f"Blog photo, 16:9, topic: {keyword}. {prompt}. "
            "Photorealistic, no text overlay, no watermark.",
            seed,
        ),
        (
            sanitize_flux_prompt(prompt, keyword=keyword),
            random.randint(0, 2_147_483_647),
        ),
    ]

    last_err: str | None = None
    for idx, (full_prompt, attempt_seed) in enumerate(attempts):
        try:
            raw, err = _call_flux(
                model_path=model_path,
                full_prompt=full_prompt,
                seed=attempt_seed,
            )
            if raw:
                _save_jpeg(raw, output_path, slot=slot)
                return output_path, None, model_path

            last_err = err
            if err != "CONTENT_FILTERED":
                break
        except httpx.TimeoutException as exc:
            last_err = f"API 응답 시간 초과 ({exc.__class__.__name__})"
            if idx == 0:
                continue
            break
        except Exception as exc:
            last_err = str(exc)
            break

    if last_err == "CONTENT_FILTERED":
        msg = (
            f"{label}: 콘텐츠 안전 필터 차단 — "
            "실존 정치인·전쟁·폭력 표현은 FLUX에서 거부됩니다. "
            "프롬프트를 상징적 장면(지도, 유조선, 뉴스룸 등)으로 바꿔 주세요."
        )
    elif last_err and "시간 초과" in last_err:
        msg = f"{label}: {last_err} (FLUX API가 느릴 때 발생, 카드 이미지로 대체)"
    else:
        msg = f"{label} ({model_path}): {last_err}"
    return None, msg, model_path
