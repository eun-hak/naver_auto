"""초안 품질 검증."""

from __future__ import annotations

import re


META_LABEL_RE = re.compile(r"^\[(?:summary|timeline|person|controversy)\]", re.I | re.M)
INFORMAL_RE = re.compile(
    r'(?<![\"\'\"])(?:^|[.!?]\s+)[^#\n>\"]{0,80}?(?:한다|간다|온다|된다|이다|였다|했다|겠다|할게)\.',
    re.M,
)
FORMAL_RE = re.compile(
    r"(?:습니다|입니다|세요|ㅂ니다|이에요|예요|더군요|지요|인데요|드릴게요|해요|보세요)"
)


def normalize_draft_body(body: str) -> str:
    from naver_auto.publish.markdown_format import normalize_markdown_for_publish

    lines: list[str] = []
    for line in body.splitlines():
        cleaned = re.sub(
            r"^\[(?:summary|timeline|person|controversy)\]\s*", "", line, flags=re.I
        )
        cleaned = re.sub(r"<a\s+[^>]+>", "", cleaned)
        cleaned = re.sub(r"</a>", "", cleaned)
        lines.append(cleaned)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return normalize_markdown_for_publish(text)


def extract_title(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "제목 없음"


def insert_image_placeholders(body: str, count: int) -> str:
    if count <= 0:
        return body

    existing = len(re.findall(r"!\[이미지", body))
    if existing >= count:
        return body

    lines = body.splitlines()
    section_indices = [
        i for i, line in enumerate(lines) if line.strip().startswith("## ")
    ]
    needed = count - existing
    insert_at: list[int] = []

    if section_indices:
        step = max(1, len(section_indices) // needed) if needed else 1
        for idx in range(0, len(section_indices), step):
            if len(insert_at) >= needed:
                break
            insert_at.append(section_indices[idx])
    else:
        chunk = max(1, len(lines) // (needed + 1))
        for n in range(1, needed + 1):
            insert_at.append(min(n * chunk, len(lines)))

    img_num = existing + 1
    offset = 0
    for pos in sorted(insert_at):
        pos += offset
        placeholder = f"![이미지 {img_num}](images/{img_num:02d}.jpg)"
        lines.insert(pos, "")
        lines.insert(pos + 1, placeholder)
        lines.insert(pos + 2, "")
        offset += 3
        img_num += 1
        if img_num > count:
            break

    while img_num <= count:
        lines.extend(["", f"![이미지 {img_num}](images/{img_num:02d}.jpg)", ""])
        img_num += 1

    return "\n".join(lines)


def quality_check(body: str, seo_cfg: dict) -> list[str]:
    errors: list[str] = []
    min_c = seo_cfg.get("body", {}).get("min_chars", 1500)
    max_c = seo_cfg.get("body", {}).get("max_chars", 3500)
    length = len(body)
    if length < min_c * 0.7:
        errors.append(f"분량 부족 ({length}자)")
    if length > max_c * 1.3:
        errors.append(f"분량 과다 ({length}자)")

    img_min = max(1, seo_cfg.get("image_placeholder_count", 3) - 1)
    imgs = len(re.findall(r"!\[이미지", body))
    if imgs < img_min:
        errors.append(f"이미지 placeholder 부족 ({imgs}개)")

    if META_LABEL_RE.search(body):
        errors.append("메타 라벨([summary] 등) 포함")

    formal_hits = len(FORMAL_RE.findall(body))
    informal_hits = len(INFORMAL_RE.findall(body))
    if formal_hits < 8:
        errors.append(f"존댓말 부족 (존댓말 {formal_hits}회)")
    if informal_hits >= 3:
        errors.append(f"반말/해체 의심 ({informal_hits}문장)")

    if not re.search(r"[?？].*(?:보시|생각|궁금|어떻)", body):
        errors.append("독자 질문(존댓말) 없음")

    if len(re.findall(r"#\w", body)) < 3:
        errors.append("해시태그 부족")

    return errors
