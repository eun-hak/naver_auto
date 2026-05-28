"""body.md 마크다운 → 네이버 에디터용 구조화 블록."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
BULLET_RE = re.compile(r"^[\*\-]\s+(.+)$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
BOLD_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*$")
QA_LINE_RE = re.compile(r"^(Q\d+\.\s*)(.+)$", re.IGNORECASE)
ANSWER_LINE_RE = re.compile(r"^(A\d+\.\s*)(.+)$", re.IGNORECASE)


@dataclass
class TextSegment:
    text: str
    bold: bool = False


@dataclass
class FormattedLine:
    kind: str  # paragraph | bold_heading | bullet | numbered | qa_question | qa_answer | blank
    segments: list[TextSegment] = field(default_factory=list)
    indent: int = 0
    number: int | None = None


def parse_inline_segments(text: str) -> list[TextSegment]:
    """**굵게** 인라인 파싱."""
    text = text.strip()
    if not text:
        return []

    segments: list[TextSegment] = []
    pos = 0
    for match in INLINE_BOLD_RE.finditer(text):
        if match.start() > pos:
            plain = text[pos : match.start()]
            if plain:
                segments.append(TextSegment(plain, False))
        segments.append(TextSegment(match.group(1), True))
        pos = match.end()
    if pos < len(text):
        tail = text[pos:]
        if tail:
            segments.append(TextSegment(tail, False))
    if not segments:
        segments.append(TextSegment(text, False))
    return segments


def _classify_raw_line(line: str) -> FormattedLine | None:
    if not line.strip():
        return FormattedLine(kind="blank")

    indent = (len(line) - len(line.lstrip())) // 2
    stripped = line.strip()

    qa = QA_LINE_RE.match(stripped)
    if qa:
        return FormattedLine(
            kind="qa_question",
            segments=[
                TextSegment(qa.group(1), True),
                TextSegment(qa.group(2).strip(), False),
            ],
        )

    ans = ANSWER_LINE_RE.match(stripped)
    if ans:
        return FormattedLine(
            kind="qa_answer",
            segments=[
                TextSegment(ans.group(1), True),
                TextSegment(ans.group(2).strip(), False),
            ],
        )

    bold_match = BOLD_HEADING_RE.match(stripped)
    if bold_match:
        label = bold_match.group(1).strip().rstrip(":")
        return FormattedLine(
            kind="bold_heading",
            segments=[TextSegment(label, True)],
        )

    bullet_match = BULLET_RE.match(stripped)
    if bullet_match:
        return FormattedLine(
            kind="bullet",
            segments=parse_inline_segments(bullet_match.group(1)),
            indent=indent,
        )

    numbered_match = NUMBERED_RE.match(stripped)
    if numbered_match:
        return FormattedLine(
            kind="numbered",
            number=int(numbered_match.group(1)),
            segments=parse_inline_segments(numbered_match.group(2)),
            indent=indent,
        )

    return FormattedLine(kind="paragraph", segments=parse_inline_segments(stripped))


def parse_formatted_lines(text: str) -> list[FormattedLine]:
    return [_classify_raw_line(line) for line in text.splitlines()]


def _merge_paragraph_lines(lines: list[FormattedLine]) -> list[FormattedLine]:
    """짧게 잘린 문단 줄을 한 줄로 합침 (FAQ 등)."""
    merged: list[FormattedLine] = []
    buffer: list[TextSegment] = []

    def flush() -> None:
        if buffer:
            merged.append(FormattedLine(kind="paragraph", segments=buffer.copy()))
            buffer.clear()

    for line in lines:
        if line.kind != "paragraph":
            flush()
            merged.append(line)
            continue
        text = "".join(s.text for s in line.segments)
        if not buffer:
            buffer.extend(line.segments)
            continue
        prev = "".join(s.text for s in buffer)
        if prev.endswith(("-", "·", "…")) or text.startswith((".", ",", ")", "]", "」")):
            buffer.append(TextSegment(text, False))
        elif len(text) < 20 and not text.startswith(("##", "#", "Q", "A")):
            buffer.append(TextSegment(" " + text, False))
        else:
            flush()
            buffer.extend(line.segments)
    flush()
    return merged


def group_formatted_blocks(lines: list[FormattedLine]) -> list[dict[str, Any]]:
    """연속 목록·문단을 업로드용 블록으로 묶음."""
    lines = _merge_paragraph_lines(lines)
    blocks: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.kind == "blank":
            i += 1
            continue

        if line.kind == "bullet":
            items: list[list[TextSegment]] = []
            while i < len(lines) and lines[i].kind == "bullet":
                items.append(lines[i].segments)
                i += 1
            blocks.append({"type": "bullet_list", "items": items})
            continue

        if line.kind == "numbered":
            number = line.number or 1
            title = line.segments
            sub_bullets: list[list[TextSegment]] = []
            i += 1
            while i < len(lines) and lines[i].kind == "bullet":
                sub_bullets.append(lines[i].segments)
                i += 1
            blocks.append(
                {
                    "type": "numbered_section",
                    "number": number,
                    "title": title,
                    "bullets": sub_bullets,
                }
            )
            continue

        if line.kind == "bold_heading":
            blocks.append({"type": "bold_heading", "segments": line.segments})
            i += 1
            continue

        if line.kind in ("qa_question", "qa_answer"):
            segments = list(line.segments)
            i += 1
            while i < len(lines) and lines[i].kind == "paragraph":
                cont = segments_to_plain(lines[i].segments)
                if len(cont) > 60:
                    break
                if segments and not segments[-1].text.endswith(" "):
                    segments.append(TextSegment(" ", False))
                segments.extend(lines[i].segments)
                i += 1
            blocks.append({"type": line.kind, "segments": segments})
            continue

        para_lines: list[FormattedLine] = []
        while i < len(lines) and lines[i].kind == "paragraph":
            para_lines.append(lines[i])
            i += 1
        if para_lines:
            blocks.append({"type": "paragraph_group", "lines": para_lines})
    return blocks


def segments_to_plain(segments: list[TextSegment]) -> str:
    return "".join(s.text for s in segments)


def parse_text_to_blocks(text: str) -> list[dict[str, Any]]:
    """마크다운 텍스트 덩어리 → 에디터 삽입 블록."""
    lines = parse_formatted_lines(text)
    return group_formatted_blocks(lines)
