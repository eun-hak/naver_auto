"""Placeholder 이미지 카드 생성."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PALETTES = [
    ("#1a1a2e", "#e94560"),
    ("#0f3460", "#e94560"),
    ("#16213e", "#0f3460"),
    ("#2b2d42", "#ef233c"),
    ("#1b263b", "#778da9"),
    ("#212529", "#adb5bd"),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def create_card_image(
    output_path: Path,
    *,
    title: str,
    subtitle: str,
    index: int,
    width: int = 1200,
    height: int = 675,
) -> Path:
    bg, accent = PALETTES[index % len(PALETTES)]
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, height - 8), (width, height)], fill=accent)
    draw.rectangle([(40, 40), (width - 40, height - 40)], outline=accent, width=3)

    title_font = _load_font(52)
    sub_font = _load_font(28)

    draw.text((80, 120), title[:30], fill="white", font=title_font)
    draw.text((80, 220), subtitle[:40], fill=accent, font=sub_font)
    draw.text((80, height - 100), f"#{index:02d}", fill="#888888", font=sub_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=88)
    return output_path


def create_placeholder_set(
    images_dir: Path,
    *,
    keyword: str,
    count: int = 6,
) -> list[Path]:
    paths: list[Path] = []
    for i in range(1, count + 1):
        path = images_dir / f"{i:02d}.jpg"
        create_card_image(
            path,
            title=keyword,
            subtitle=f"섹션 {i}",
            index=i - 1,
        )
        paths.append(path)
    return paths
