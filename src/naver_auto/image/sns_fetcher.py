"""SNS·웹에서 키워드 관련 이미지 수집."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from PIL import Image

from naver_auto.paths import USER_AGENT, naver_api_configured

OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)
TWITTER_IMAGE_RE = re.compile(
    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)

SNS_DOMAINS = {
    "instagram.com": "instagram",
    "pinimg.com": "pinterest",
    "pinterest.com": "pinterest",
    "pinterest.co.kr": "pinterest",
    "post.naver.com": "naver_post",
    "blog.naver.com": "naver_blog",
    "tistory.com": "tistory",
}


@dataclass
class SocialImage:
    image_url: str
    source: str
    title: str
    page_url: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _detect_source(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for domain, name in SNS_DOMAINS.items():
        if domain in host:
            return name
    return "web"


def _search_naver_images(query: str, *, display: int = 10) -> list[SocialImage]:
    if not naver_api_configured():
        return []

    from naver_auto.keyword.analyzer import search_naver

    try:
        data = search_naver(query, "image", display=display, sort="sim")
    except Exception:
        return []

    results: list[SocialImage] = []
    for item in data.get("items", []):
        link = str(item.get("link", "")).strip()
        thumb = str(item.get("thumbnail", "")).strip()
        title = re.sub(r"<[^>]+>", "", str(item.get("title", "")))
        image_url = link if _looks_like_image_url(link) else thumb
        if not image_url:
            continue
        page_url = link if link and not _looks_like_image_url(link) else ""
        source = _detect_source(page_url or image_url)
        if "instagram" in query.lower():
            source = "instagram"
        elif "pinterest" in query.lower():
            source = "pinterest"
        results.append(
            SocialImage(
                image_url=image_url,
                source=source,
                title=title,
                page_url=page_url or image_url,
            )
        )
    return results


def _looks_like_image_url(url: str) -> bool:
    lower = url.lower()
    if any(ext in lower for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return True
    return any(
        token in lower
        for token in ("pstatic.net", "pinimg.com", "cdninstagram", "fbcdn.net", "postfiles")
    )


def _extract_og_image(html: str, base_url: str) -> str | None:
    for pattern in (OG_IMAGE_RE, OG_IMAGE_RE_ALT, TWITTER_IMAGE_RE):
        match = pattern.search(html)
        if match:
            return urljoin(base_url, match.group(1).strip())
    return None


def fetch_og_from_pages(page_urls: list[str], *, limit: int = 10) -> list[SocialImage]:
    results: list[SocialImage] = []
    seen: set[str] = set()

    with httpx.Client(
        timeout=20.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for page_url in page_urls:
            if len(results) >= limit:
                break
            if not page_url or page_url in seen:
                continue
            seen.add(page_url)
            try:
                res = client.get(page_url)
                res.raise_for_status()
                og = _extract_og_image(res.text, str(res.url))
                if not og:
                    continue
                results.append(
                    SocialImage(
                        image_url=og,
                        source=_detect_source(page_url),
                        title="",
                        page_url=page_url,
                    )
                )
            except Exception:
                continue
    return results


def build_search_queries(keyword: str, cfg: dict[str, Any]) -> list[str]:
    templates = cfg.get(
        "search_queries",
        [
            "{keyword}",
            "{keyword} 맛집",
            "{keyword} site:instagram.com",
            "{keyword} site:pinterest.com",
        ],
    )
    return [t.format(keyword=keyword) for t in templates]


def collect_social_images(
    keyword: str,
    *,
    references: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[SocialImage]:
    cfg = cfg or {}
    limit = int(cfg.get("max_candidates", 20))
    results: list[SocialImage] = []
    seen_urls: set[str] = set()

    def add(items: list[SocialImage]) -> None:
        for item in items:
            key = item.image_url.split("?")[0]
            if key in seen_urls:
                continue
            seen_urls.add(key)
            results.append(item)
            if len(results) >= limit:
                return

    ref_urls = [str(r.get("link", "")) for r in (references or []) if r.get("link")]
    add(fetch_og_from_pages(ref_urls, limit=min(8, limit)))

    per_query = int(cfg.get("per_query", 8))
    for query in build_search_queries(keyword, cfg):
        if len(results) >= limit:
            break
        add(_search_naver_images(query, display=per_query))

    prefer = cfg.get("prefer_sources", ["instagram", "pinterest", "naver_blog", "naver_post"])
    order = {name: idx for idx, name in enumerate(prefer)}

    def sort_key(item: SocialImage) -> tuple[int, str]:
        return (order.get(item.source, 99), item.image_url)

    return sorted(results, key=sort_key)[:limit]


def download_as_jpeg(
    image: SocialImage,
    output_path: Path,
    *,
    min_width: int = 400,
    min_height: int = 300,
    target_size: tuple[int, int] | None = (1200, 675),
) -> bool:
    try:
        with httpx.Client(
            timeout=25.0,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Referer": image.page_url},
        ) as client:
            res = client.get(image.image_url)
            res.raise_for_status()
            raw = res.content
    except Exception:
        return False

    try:
        img = Image.open(BytesIO(raw))
        if img.width < min_width or img.height < min_height:
            return False
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        if target_size:
            img = _fit_cover(img, target_size[0], target_size[1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "JPEG", quality=88)
        return True
    except Exception:
        return False


def _fit_cover(img: Image.Image, width: int, height: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    return resized.crop((left, top, left + width, top + height))


def fetch_images_for_slots(
    keyword: str,
    *,
    slot_count: int,
    references: list[dict[str, Any]] | None = None,
    cfg: dict[str, Any] | None = None,
    images_dir: Path,
) -> tuple[list[Path], list[dict[str, str]]]:
    candidates = collect_social_images(keyword, references=references, cfg=cfg)
    saved: list[PathType] = []
    attributions: list[dict[str, str]] = []
    used_hashes: set[str] = set()

    for candidate in candidates:
        if len(saved) >= slot_count:
            break
        digest = hashlib.md5(candidate.image_url.encode()).hexdigest()[:8]
        if digest in used_hashes:
            continue
        out_path = images_dir / f"{len(saved) + 1:02d}.jpg"
        if download_as_jpeg(candidate, out_path, min_width=int((cfg or {}).get("min_width", 400))):
            used_hashes.add(digest)
            saved.append(out_path)
            attributions.append(candidate.to_dict())

    return saved, attributions
