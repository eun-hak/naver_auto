"""body.md 마크다운 → 네이버 에디터용 구조화 블록."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
BULLET_RE = re.compile(r"^[\*\-]\s+(.+)$")
NUMBERED_RE = re.compile(r"^(\d+)\.\s+(.+)$")
HR_LINE_RE = re.compile(r"^[-*_]{3,}\s*$")
WRAPPED_LINE_RE = re.compile(r"^\*\*(.+?)\*\*:?\s*$")
QA_LINE_RE = re.compile(r"^(Q\d+[\.:]\s*)(.+)$", re.IGNORECASE)
ANSWER_LINE_RE = re.compile(r"^(A\d+[\.:]\s*)(.+)$", re.IGNORECASE)


def _normalize_qa_label(label: str) -> str:
    """Q1: / A1: → Q1. / A1. (네이버 입력·프롬프트와 통일)."""
    return re.sub(r"^([QA])(\d+):", r"\1\2.", label, flags=re.IGNORECASE)


@dataclass
class TextSegment:
    text: str
    bold: bool = False


@dataclass
class FormattedLine:
    kind: str  # paragraph | bold_heading | bullet | numbered | qa_question | qa_answer | blank | hr
    segments: list[TextSegment] = field(default_factory=list)
    indent: int = 0
    number: int | None = None


def _unwrap_line(stripped: str) -> str:
    """`**전체 줄**` → 내부 텍스트."""
    m = WRAPPED_LINE_RE.match(stripped)
    if m:
        return m.group(1).strip()
    return stripped


def parse_inline_segments(text: str) -> list[TextSegment]:
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


def _classify_raw_line(line: str) -> FormattedLine:
    if not line.strip():
        return FormattedLine(kind="blank")

    indent = (len(line) - len(line.lstrip())) // 2
    stripped = line.strip()

    if HR_LINE_RE.match(stripped):
        return FormattedLine(kind="hr")

    inner = _unwrap_line(stripped)

    qa = QA_LINE_RE.match(inner)
    if qa:
        label = _normalize_qa_label(qa.group(1))
        return FormattedLine(
            kind="qa_question",
            segments=[
                TextSegment(label, True),
                TextSegment(qa.group(2).strip(), False),
            ],
        )

    ans = ANSWER_LINE_RE.match(inner)
    if ans:
        label = _normalize_qa_label(ans.group(1))
        return FormattedLine(
            kind="qa_answer",
            segments=[
                TextSegment(label, True),
                TextSegment(ans.group(2).strip(), False),
            ],
        )

    # FAQ 질문이 아닌 굵은 한 줄 제목만 (Q/A, FAQ 헤더 제외)
    if WRAPPED_LINE_RE.match(stripped):
        label = inner.strip().rstrip(":")
        if not QA_LINE_RE.match(label) and not ANSWER_LINE_RE.match(label):
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
    if numbered_match and not QA_LINE_RE.match(inner):
        return FormattedLine(
            kind="numbered",
            number=int(numbered_match.group(1)),
            segments=parse_inline_segments(numbered_match.group(2)),
            indent=indent,
        )

    return FormattedLine(kind="paragraph", segments=parse_inline_segments(stripped))


def _is_structural_line(stripped: str) -> bool:
    if not stripped:
        return True
    if HR_LINE_RE.match(stripped):
        return True
    if stripped.startswith(("#", "!", "|")):
        return True
    inner = _unwrap_line(stripped)
    if QA_LINE_RE.match(inner) or ANSWER_LINE_RE.match(inner):
        return True
    if BULLET_RE.match(stripped) or NUMBERED_RE.match(stripped):
        return True
    return False


def _should_merge_continuation(prev_plain: str, next_plain: str) -> bool:
    if not prev_plain or not next_plain:
        return False
    if _is_structural_line(next_plain):
        return False
    prev = prev_plain.rstrip()
    if prev.endswith((".", "?", "!", "…", "다", "요", "니다", "습니다")):
        return False
    if HR_LINE_RE.match(next_plain):
        return False
    if len(next_plain) < 48:
        return True
    inner_prev = _unwrap_line(prev)
    if QA_LINE_RE.match(inner_prev) and len(inner_prev) < 40:
        return True
    return False


def _finalize_line(line: str) -> str:
    """병합 후 깨진 `**`·FAQ 형식 복구."""
    stripped = line.strip()
    if not stripped:
        return ""
    if HR_LINE_RE.match(stripped):
        return ""
    # 중간에 남은 ** 제거 후 FAQ 재포장
    plain = stripped.replace("**", "").strip()
    qa = QA_LINE_RE.match(plain)
    if qa:
        label = _normalize_qa_label(qa.group(1))
        return f"**{label}{qa.group(2).strip()}**"
    ans = ANSWER_LINE_RE.match(plain)
    if ans:
        label = _normalize_qa_label(ans.group(1))
        return f"{label}{ans.group(2).strip()}"
    return stripped


def normalize_markdown_for_publish(text: str) -> str:
    """업로드 전: --- 제거, 잘린 줄 병합, FAQ 형식 정리."""
    lines = text.splitlines()
    merged: list[str] = []

    for line in lines:
        stripped = line.strip()
        if HR_LINE_RE.match(stripped):
            if merged and merged[-1].strip():
                merged.append("")
            continue
        if merged and _should_merge_continuation(merged[-1].strip(), stripped):
            merged[-1] = merged[-1].rstrip() + " " + stripped
            continue
        merged.append(line)

    finalized = [_finalize_line(ln) for ln in merged]
    finalized = [ln for ln in finalized if ln.strip() or ln == ""]
    text = "\n".join(finalized)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_formatted_lines(text: str) -> list[FormattedLine]:
    text = normalize_markdown_for_publish(text)
    return [_classify_raw_line(line) for line in text.splitlines()]


def _merge_paragraph_lines(lines: list[FormattedLine]) -> list[FormattedLine]:
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
        if _should_merge_continuation(prev, text):
            if not prev.endswith(" ") and not text.startswith((" ", ".", ",")):
                buffer.append(TextSegment(" ", False))
            buffer.extend(line.segments)
        else:
            flush()
            buffer.extend(line.segments)
    flush()
    return merged


def group_formatted_blocks(lines: list[FormattedLine]) -> list[dict[str, Any]]:
    lines = _merge_paragraph_lines(lines)
    blocks: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.kind in ("blank", "hr"):
            blocks.append({"type": "spacer"})
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
                if len(cont) > 80:
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
    lines = parse_formatted_lines(text)
    return group_formatted_blocks(lines)
