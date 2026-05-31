"""수집·생성 이미지 후처리 — 워터마크, 색감, 크롭 등."""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def load_postprocess_cfg() -> dict[str, Any]:
    from naver_auto.paths import load_yaml

    return load_yaml("publish.yaml").get("image_postprocess", {}) or {}


def should_apply(source: str, cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or load_postprocess_cfg()
    if not cfg.get("enabled", False):
        return False
    targets = cfg.get("apply_to", ["sns", "gemini"])
    return source in targets


def _resolve_watermark_text(raw: str) -> str:
    blog_id = os.getenv("NAVER_BLOG_ID", "").strip()
    return raw.replace("{blog_id}", blog_id or "blog").strip()


def _crop_jitter(img: Image.Image, ratio: float, slot: int) -> Image.Image:
    if ratio <= 0:
        return img
    w, h = img.size
    rng = random.Random(slot * 7919 + w + h)
    max_cut = int(min(w, h) * ratio)
    if max_cut < 2:
        return img
    left = rng.randint(0, max_cut)
    top = rng.randint(0, max_cut)
    right = w - rng.randint(0, max_cut)
    bottom = h - rng.randint(0, max_cut)
    if right - left < w * 0.85 or bottom - top < h * 0.85:
        return img
    return img.crop((left, top, right, bottom))


def _adjust_color(img: Image.Image, *, slot: int, cfg: dict[str, Any]) -> Image.Image:
    tcfg = cfg.get("transforms", {})
    rng = random.Random(slot * 3571 + img.size[0])

    bright = float(tcfg.get("brightness_jitter", 0.04))
    if bright > 0:
        img = ImageEnhance.Brightness(img).enhance(1.0 + rng.uniform(-bright, bright))

    contrast = float(tcfg.get("contrast", 1.0))
    if contrast != 1.0:
        jitter = float(tcfg.get("contrast_jitter", 0.03))
        img = ImageEnhance.Contrast(img).enhance(max(0.5, contrast + rng.uniform(-jitter, jitter)))

    saturation = float(tcfg.get("saturation", 1.0))
    if saturation != 1.0:
        jitter = float(tcfg.get("saturation_jitter", 0.05))
        img = ImageEnhance.Color(img).enhance(max(0.5, saturation + rng.uniform(-jitter, jitter)))

    sharpness = float(tcfg.get("sharpness", 1.0))
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)

    rotate = float(tcfg.get("rotate_deg", 0))
    if rotate > 0:
        img = img.rotate(
            rng.uniform(-rotate, rotate),
            resample=Image.Resampling.BICUBIC,
            expand=False,
        )

    return img


def _vignette(img: Image.Image, strength: float) -> Image.Image:
    if strength <= 0:
        return img
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        (-int(w * 0.15), -int(h * 0.15), int(w * 1.15), int(h * 1.15)),
        fill=int(255 * (1 - strength)),
    )
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, dark, mask)


def _apply_watermark(img: Image.Image, wcfg: dict[str, Any]) -> Image.Image:
    if not wcfg.get("enabled", True):
        return img

    text = _resolve_watermark_text(str(wcfg.get("text", "{blog_id}")))
    if not text:
        return img

    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = int(wcfg.get("font_size", 26))
    font = _load_font(font_size)
    opacity = int(float(wcfg.get("opacity", 0.35)) * 255)
    position = str(wcfg.get("position", "bottom_right")).lower()
    padding = int(wcfg.get("padding", 24))

    if position == "tile":
        step_x = max(180, font_size * max(4, len(text)))
        step_y = max(100, font_size * 3)
        for y in range(0, base.height + step_y, step_y):
            for x in range(0, base.width + step_x, step_x):
                draw.text((x, y), text, fill=(255, 255, 255, opacity), font=font)
    else:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        positions = {
            "bottom_right": (base.width - tw - padding, base.height - th - padding),
            "bottom_left": (padding, base.height - th - padding),
            "top_right": (base.width - tw - padding, padding),
            "top_left": (padding, padding),
            "center": ((base.width - tw) // 2, (base.height - th) // 2),
        }
        xy = positions.get(position, positions["bottom_right"])
        draw.text(xy, text, fill=(255, 255, 255, opacity), font=font)

    return Image.alpha_composite(base, overlay).convert("RGB")


def _add_border(img: Image.Image, bcfg: dict[str, Any]) -> Image.Image:
    if not bcfg.get("enabled", False):
        return img
    width = int(bcfg.get("width", 4))
    color = str(bcfg.get("color", "#ffffff"))
    return ImageOps.expand(img, border=width, fill=color)


def apply_postprocess(
    img: Image.Image,
    *,
    source: str = "sns",
    slot: int = 1,
    cfg: dict[str, Any] | None = None,
) -> Image.Image:
    cfg = cfg or load_postprocess_cfg()
    if not should_apply(source, cfg):
        return img

    if img.mode != "RGB":
        img = img.convert("RGB")

    tcfg = cfg.get("transforms", {})
    img = _crop_jitter(img, float(tcfg.get("crop_jitter", 0.02)), slot)
    img = _adjust_color(img, slot=slot, cfg=cfg)

    if tcfg.get("vignette", False):
        img = _vignette(img, float(tcfg.get("vignette_strength", 0.15)))

    img = _apply_watermark(img, cfg.get("watermark", {}))
    img = _add_border(img, cfg.get("border", {}))
    return img


def save_processed_jpeg(
    img: Image.Image,
    output_path: Path,
    *,
    source: str = "sns",
    slot: int = 1,
    quality: int = 88,
    cfg: dict[str, Any] | None = None,
) -> None:
    cfg = cfg or load_postprocess_cfg()
    processed = apply_postprocess(img, source=source, slot=slot, cfg=cfg)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, Any] = {"format": "JPEG", "quality": quality}
    if cfg.get("strip_exif", True):
        save_kwargs["exif"] = b""
    processed.save(output_path, **save_kwargs)
