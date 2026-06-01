"""짧은 사용자 이미지 지시 -> FLUX용 영문 프롬프트 확장 (NVIDIA Llama 3.1 8B)."""

from __future__ import annotations

import os
import re

DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"
DEFAULT_MIN_LENGTH = 72


def _cfg() -> dict:
    from naver_auto.paths import load_yaml

    return load_yaml("publish.yaml").get("image_prompt_expand", {}) or {}


def expand_enabled() -> bool:
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return False
    return bool(os.getenv("NVIDIA_API_KEY"))


def _model() -> str:
    return str(_cfg().get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _min_length() -> int:
    return int(_cfg().get("min_length", DEFAULT_MIN_LENGTH))


def needs_expansion(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if len(t) >= _min_length() * 2:
        return False
    if len(t) >= _min_length() and re.search(
        r"(photorealistic|editorial|natural light|depth of field|shallow|35mm|no text)",
        t,
        re.I,
    ):
        return False
    return True


def expand_image_prompt(
    brief: str,
    *,
    keyword: str,
    title: str = "",
    section: str = "",
) -> str:
    """짧은 한/영 지시를 FLUX용 영문 프롬프트로 확장. 실패 시 원문 반환."""
    brief = brief.strip()
    if not brief or not needs_expansion(brief):
        return brief
    if not expand_enabled():
        return brief

    system = (
        "You expand brief image direction into one English FLUX image generation prompt.\n"
        "Rules:\n"
        "- Output ONLY the prompt text, no quotes, no markdown\n"
        "- Photorealistic editorial blog photo\n"
        "- Include scene, lighting, composition, lens feel (e.g. 35mm, shallow DOF)\n"
        "- no text, no logos, no watermark\n"
        "- No real politician names, no war violence, no weapons — "
        "use symbolic neutral scenes for geopolitics\n"
        "- Korean input -> translate intent to English visual description"
    )
    user = (
        f"Keyword: {keyword}\n"
        f"Article title: {title or keyword}\n"
        f"Section: {section or 'general'}\n"
        f"User brief (may be Korean): {brief}\n\n"
        "Write one detailed FLUX prompt (2-4 sentences, under 280 characters):"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=60.0,
        )
        response = client.chat.completions.create(
            model=_model(),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
            max_tokens=256,
        )
        out = (response.choices[0].message.content or "").strip()
        out = re.sub(r'^["\']|["\']$', "", out)
        out = re.sub(r"\s+", " ", out).strip()
        return out if out else brief
    except Exception:
        return brief


def default_slot_prompt(
    *,
    keyword: str,
    title: str = "",
    section: str = "",
    slot_plan: dict | None = None,
) -> str:
    """슬롯별 기본 FLUX 프롬프트 — image_plan 우선, 없으면 Llama로 키워드+섹션 확장."""
    planned = str((slot_plan or {}).get("gemini_prompt") or "").strip()
    if planned:
        return planned
    sec = section.strip()
    if sec.startswith("섹션 "):
        sec = ""
    brief = f"{keyword}, {sec}" if sec and sec != keyword else keyword
    expanded = expand_image_prompt(brief, keyword=keyword, title=title, section=sec or section)
    if expanded != brief:
        return expanded
    return f"{brief}, editorial photo, natural light, shallow depth of field, no text"


def expand_slot_prompts(
    slot_prompts: dict[str, str] | dict[int, str],
    *,
    keyword: str,
    title: str = "",
) -> dict[str, str]:
    """슬롯별 짧은 프롬프트 -> FLUX용 영문 확장."""
    expanded: dict[str, str] = {}
    for key, val in slot_prompts.items():
        raw = str(val).strip()
        if not raw:
            continue
        slot = str(int(key))
        expanded[slot] = expand_image_prompt(raw, keyword=keyword, title=title)
    return expanded


def slot_prompts_from_meta(
    meta: dict,
    *,
    keyword: str,
    title: str = "",
) -> dict[int, str]:
    """meta에 저장된 슬롯별 확장 프롬프트."""
    result: dict[int, str] = {}
    exp = meta.get("slot_image_prompts_expanded") or {}
    for key, val in exp.items():
        text = str(val).strip()
        if text:
            result[int(key)] = text
    if result:
        return result
    raw_map = meta.get("slot_image_prompts") or {}
    for key, val in raw_map.items():
        raw = str(val).strip()
        if raw:
            result[int(key)] = expand_image_prompt(raw, keyword=keyword, title=title)
    return result
