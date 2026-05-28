"""Smart Editor ONE — 제목·본문·이미지 입력 (iframe 지원)."""

from __future__ import annotations

import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Frame, Page, TimeoutError as PlaywrightTimeout

from naver_auto.publish.editor_context import (
    EditorRoot,
    PARAGRAPH,
    body_paragraph_locator,
    detect_editor_ids,
    editor_keyboard,
    find_editor_root,
    resolve_body_focus_locator,
    resolve_editor_root,
    resolve_last_body_paragraph,
    resolve_title_locator,
    title_element_id,
)


def log(msg: str) -> None:
    print(f"  [editor] {msg}", flush=True)


DRAFT_RESUME_TEXT = "작성 중인 글이"
DRAFT_CANCEL_BTN = ".se-popup-button.se-popup-button-cancel"


def _popup_targets(page: Page, root: EditorRoot | None = None) -> list[EditorRoot | Page]:
    targets: list[EditorRoot | Page] = []
    for t in (root, page):
        if t is not None and t not in targets:
            targets.append(t)
    return targets


def dismiss_draft_resume_popup(page: Page, root: EditorRoot | None = None) -> bool:
    """'작성 중인 글이 있습니다' 팝업 → 취소 (새 글 작성)."""
    for target in _popup_targets(page, root):
        cancel = target.locator(DRAFT_CANCEL_BTN).first
        if cancel.count() > 0:
            try:
                if cancel.is_visible():
                    log("이전 작성 중 글 팝업 → 취소")
                    cancel.click(timeout=3000)
                    time.sleep(0.5)
                    return True
            except (PlaywrightTimeout, Exception):
                pass

        if target.get_by_text(DRAFT_RESUME_TEXT).count() == 0:
            continue

        for sel in (DRAFT_CANCEL_BTN, ".se-popup-button-cancel"):
            btn = target.locator(sel).first
            if btn.count() == 0:
                continue
            try:
                btn.click(timeout=3000)
                log("이전 작성 중 글 팝업 → 취소")
                time.sleep(0.5)
                return True
            except PlaywrightTimeout:
                pass

        cancel_role = target.get_by_role("button", name="취소")
        if cancel_role.count() > 0:
            try:
                cancel_role.first.click(timeout=3000)
                log("이전 작성 중 글 팝업 → 취소")
                time.sleep(0.5)
                return True
            except PlaywrightTimeout:
                pass
    return False


def dismiss_popups(page: Page, root: EditorRoot | None = None) -> None:
    dismiss_draft_resume_popup(page, root)
    for target in _popup_targets(page, root):
        for name in ("닫기", "다음에 보지 않기"):
            btn = target.get_by_role("button", name=name)
            if btn.count() > 0:
                try:
                    btn.first.click(timeout=1500)
                    time.sleep(0.3)
                except PlaywrightTimeout:
                    pass
        if target.get_by_text(DRAFT_RESUME_TEXT).count() == 0:
            btn = target.get_by_role("button", name="확인")
            if btn.count() > 0:
                try:
                    btn.first.click(timeout=1500)
                    time.sleep(0.3)
                except PlaywrightTimeout:
                    pass


DEVICE_DESKTOP_BTN = ".se-util-button.__mode-button.se-util-button-device-desktop"
DEVICE_MOBILE_BTN = ".se-util-button.__mode-button.se-util-button-device-mobile"


def switch_to_mobile_preview(page: Page, root: EditorRoot) -> bool:
    """글 작성 전 모바일 미리보기(모바일 환경)로 전환."""
    log("모바일 미리보기 모드 전환…")
    dismiss_popups(page, root=root)

    targets: list[EditorRoot] = []
    for t in (root, page):
        if t is not None and t not in targets:
            targets.append(t)

    for target in targets:
        mobile = target.locator(DEVICE_MOBILE_BTN).first
        if mobile.count() > 0:
            try:
                if mobile.is_visible():
                    log("이미 모바일 모드")
                    return True
            except Exception:
                pass

    for target in targets:
        btn = target.locator(DEVICE_DESKTOP_BTN).first
        if btn.count() == 0:
            btn = target.locator(".se-util-button-device-desktop").first
        if btn.count() == 0:
            continue
        try:
            btn.scroll_into_view_if_needed(timeout=3000)
            btn.click(timeout=8000)
            time.sleep(0.8)
            for t in targets:
                if t.locator(DEVICE_MOBILE_BTN).count() > 0:
                    log("모바일 모드 전환 완료")
                    _log_detected_ids(root)
                    return True
            log("모바일 모드 전환 (확인 생략)")
            _log_detected_ids(root)
            return True
        except PlaywrightTimeout:
            continue

    log("모바일 전환 버튼 없음 — 데스크톱 모드로 계속")
    return False


def _log_detected_ids(root: EditorRoot) -> None:
    title_id, body_id = detect_editor_ids(root)
    env_title = title_element_id()
    if title_id and title_id != env_title:
        log(f"제목 id 자동탐지: {title_id} (env와 다름)")
    if body_id:
        log(f"본문 id: {body_id}")


def wait_editor_ready(page: Page, root: EditorRoot | None = None) -> EditorRoot:
    if root is not None:
        dismiss_popups(page, root=root)
        log("에디터 로드 완료 (재사용)")
        _log_detected_ids(root)
        return root
    dismiss_popups(page)
    found = find_editor_root(page)
    if found:
        dismiss_popups(page, root=found)
        log("에디터 로드 완료")
        _log_detected_ids(found)
        return found
    root = resolve_editor_root(page, timeout_sec=45)
    dismiss_popups(page, root=root)
    log("에디터 로드 완료")
    _log_detected_ids(root)
    return root


FONT_SIZE_BTN = "button.se-font-size-code-toolbar-button"
FONT_SIZE_OPTION = "button.se-toolbar-option-font-size-code-fs{size}-button"
BOLD_BTN_SELECTORS = (
    "button.se-bold-toolbar-button",
    "button[data-name='bold']",
    ".se-toolbar-item-bold button",
)
DEFAULT_BODY_FONT_SIZE = 15


def _click_title(root: EditorRoot) -> None:
    loc = resolve_title_locator(root)
    loc.click(timeout=8000)
    time.sleep(0.4)


def _toolbar_locator(root: EditorRoot, page: Page, selector: str):
    for target in (root, page):
        loc = target.locator(selector).first
        if loc.count() > 0:
            return loc
    return root.locator(selector).first


def _select_current_line(page: Page, root: EditorRoot) -> None:
    kb = editor_keyboard(page, root)
    kb.press("End")
    time.sleep(0.05)
    kb.press("Shift+Home")
    time.sleep(0.25)


def _select_paragraph_text(page: Page, root: EditorRoot) -> None:
    """문단 전체 선택 — 줄바꿈된 소제목도 포함 (Shift+Home은 마지막 줄만)."""
    para = resolve_last_body_paragraph(root)
    if para.count() > 0:
        try:
            para.click(timeout=3000)
            time.sleep(0.1)
            para.click(click_count=3, timeout=3000)
            time.sleep(0.25)
            return
        except PlaywrightTimeout:
            pass
    _select_current_line(page, root)


def _apply_font_size(page: Page, root: EditorRoot, size: int) -> None:
    btn = _toolbar_locator(root, page, FONT_SIZE_BTN)
    btn.click(timeout=4000)
    time.sleep(0.25)
    option_sel = FONT_SIZE_OPTION.format(size=size)
    option = _toolbar_locator(root, page, option_sel)
    option.click(timeout=4000)
    time.sleep(0.25)


def _apply_bold(page: Page, root: EditorRoot) -> None:
    for sel in BOLD_BTN_SELECTORS:
        btn = _toolbar_locator(root, page, sel)
        if btn.count() == 0:
            continue
        try:
            btn.click(timeout=4000)
            time.sleep(0.25)
            return
        except PlaywrightTimeout:
            continue
    log("굵게 버튼 없음 — 건너뜀")


def _bold_is_active(page: Page, root: EditorRoot) -> bool:
    for sel in BOLD_BTN_SELECTORS:
        btn = _toolbar_locator(root, page, sel)
        if btn.count() == 0:
            continue
        classes = btn.get_attribute("class") or ""
        if "se-is-selected" in classes:
            return True
        if btn.get_attribute("aria-pressed") == "true":
            return True
    return False


def _turn_off_bold(page: Page, root: EditorRoot) -> None:
    if _bold_is_active(page, root):
        _apply_bold(page, root)


def _reset_typing_style(page: Page, root: EditorRoot) -> None:
    """소제목 스타일이 다음 본문에 이어지지 않도록 기본값으로 복원."""
    para = resolve_last_body_paragraph(root)
    if para.count() > 0:
        try:
            para.click(timeout=2000)
            time.sleep(0.1)
        except PlaywrightTimeout:
            pass
    _apply_font_size(page, root, DEFAULT_BODY_FONT_SIZE)
    _turn_off_bold(page, root)


def _apply_subheading_style(page: Page, root: EditorRoot, *, level: int) -> None:
    size = 24 if level <= 2 else 19
    _select_paragraph_text(page, root)
    _apply_font_size(page, root, size)
    if not _bold_is_active(page, root):
        _apply_bold(page, root)


def _enable_subheading_typing_style(page: Page, root: EditorRoot, *, level: int) -> None:
    """입력 전 24pt+굵게 — 줄바꿈돼도 전체에 스타일 적용."""
    para = resolve_last_body_paragraph(root)
    if para.count() > 0:
        try:
            para.click(timeout=3000)
            time.sleep(0.1)
        except PlaywrightTimeout:
            pass
    size = 24 if level <= 2 else 19
    _apply_font_size(page, root, size)
    if not _bold_is_active(page, root):
        _apply_bold(page, root)


def _new_body_line(page: Page, root: EditorRoot) -> None:
    _focus_at_end(page, root)
    kb = editor_keyboard(page, root)
    before = body_paragraph_locator(root).count()
    kb.press("Enter")
    time.sleep(0.3)
    deadline = time.time() + 2.0
    while time.time() < deadline and body_paragraph_locator(root).count() <= before:
        time.sleep(0.1)


def _focus_at_end(page: Page, root: EditorRoot) -> None:
    """본문 맨 아래로 커서 이동 (이미지·텍스트 블록마다 호출)."""
    kb = editor_keyboard(page, root)
    loc = resolve_body_focus_locator(root)
    if loc.count() == 0:
        raise RuntimeError("본문 영역을 찾지 못했습니다.")
    loc.click(timeout=8000)

    time.sleep(0.15)
    mod = "Meta" if sys.platform == "darwin" else "Control"
    kb.press(f"{mod}+ArrowDown")
    time.sleep(0.1)
    kb.press("End")
    time.sleep(0.1)


def _type_in_paragraph(page: Page, root: EditorRoot, plain: str) -> None:
    """본문 문단에 텍스트 입력 — 클릭 실패 시 키보드 fallback."""
    kb = editor_keyboard(page, root)
    delay = random.randint(3, 8)
    para = resolve_last_body_paragraph(root)

    if para.count() > 0:
        for click_force in (False, True):
            try:
                if click_force:
                    para.click(force=True, timeout=3000)
                else:
                    para.scroll_into_view_if_needed(timeout=2000)
                    para.click(timeout=3000)
                para.press_sequentially(plain, delay=delay)
                return
            except PlaywrightTimeout:
                continue
        try:
            para.focus(timeout=2000)
            para.press_sequentially(plain, delay=delay)
            return
        except PlaywrightTimeout:
            pass

    log("문단 클릭 실패 — 키보드 직접 입력")
    kb.type(plain, delay=delay)


def insert_text(page: Page, text: str, *, root: EditorRoot) -> None:
    plain = markdown_to_plain(text)
    if not plain.strip():
        return
    log(f"본문 블록 ({len(plain)}자)…")
    _new_body_line(page, root)
    _reset_typing_style(page, root)
    _type_in_paragraph(page, root, plain)
    editor_keyboard(page, root).press("Enter")
    time.sleep(0.35)


def insert_subheading(page: Page, text: str, *, root: EditorRoot, level: int = 2) -> None:
    """## / ### → 글자 24(또는 19) + 굵게."""
    if not text.strip():
        return
    label = "소제목" if level <= 2 else "소소제목"
    plain = text.strip()
    log(f"{label} ({len(plain)}자)…")
    _new_body_line(page, root)
    _reset_typing_style(page, root)
    _enable_subheading_typing_style(page, root, level=level)
    kb = editor_keyboard(page, root)
    kb.type(plain, delay=random.randint(3, 8))
    time.sleep(0.15)
    _apply_subheading_style(page, root, level=level)
    kb.press("End")
    time.sleep(0.1)
    kb.press("Enter")
    time.sleep(0.2)
    _reset_typing_style(page, root)


def fill_title(page: Page, title: str, *, root: EditorRoot) -> None:
    title_loc = resolve_title_locator(root)
    title_id = title_loc.get_attribute("id") or title_element_id()
    log(f"제목 입력 (#{title_id}, {len(title)}자)…")
    _click_title(root)
    kb = editor_keyboard(page, root)
    mod = "Meta" if sys.platform == "darwin" else "Control"
    kb.press(f"{mod}+A")
    time.sleep(0.1)
    kb.press("Backspace")
    time.sleep(0.2)
    kb.type(title, delay=random.randint(25, 45))
    time.sleep(0.5)


def markdown_to_plain(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            lines.append(stripped[3:].strip())
            lines.append("")
        elif stripped.startswith("### "):
            lines.append(stripped[4:].strip())
            lines.append("")
        elif stripped.startswith("> "):
            lines.append(stripped[2:].strip())
        elif stripped.startswith("- "):
            lines.append(f"• {stripped[2:].strip()}")
        elif stripped.startswith("#"):
            continue
        else:
            lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def upload_image(page: Page, image_path: Path, *, root: EditorRoot) -> None:
    log(f"이미지: {image_path.name}")
    _focus_at_end(page, root)
    kb = editor_keyboard(page, root)
    kb.press("Enter")
    time.sleep(0.25)

    try:
        with page.expect_file_chooser(timeout=10000) as fc_info:
            clicked = False
            for sel in (
                "button.se-image-toolbar-button",
                "li.se-toolbar-item-image button",
                "button[data-name='image']",
            ):
                btn = root.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    clicked = True
                    break
            if not clicked:
                root.locator(".se-toolbar").get_by_text("사진", exact=True).first.click()
        fc_info.value.set_files(str(image_path.resolve()))
        time.sleep(3)
    except PlaywrightTimeout as exc:
        save_debug(page, "image_upload_fail")
        raise RuntimeError(f"이미지 업로드 실패: {image_path.name}") from exc

    _focus_at_end(page, root)
    kb.press("Enter")
    time.sleep(0.25)


def set_tags(page: Page, tags: str, *, root: EditorRoot | None = None) -> None:
    if not tags.strip():
        return
    log("태그 입력…")
    tag_list = [t.strip().lstrip("#") for t in re.split(r"[,\s#]+", tags) if t.strip()]
    for target in (page, root) if root else (page,):
        if target is None:
            continue
        for sel in ("input#tagInput", "input[name='tag']", ".tag_input__ input", ".tag_input__"):
            loc = target.locator(sel).first
            if loc.count() == 0:
                continue
            for tag in tag_list[:10]:
                loc.click()
                loc.fill(tag)
                page.keyboard.press("Enter")
                time.sleep(0.25)
            return


def save_draft(page: Page, *, root: EditorRoot | None = None) -> None:
    log("저장 클릭…")
    dismiss_popups(page, root=root)
    targets = [page]
    if root is not None and root is not page:
        targets.append(root)
    for target in targets:
        for btn in (
            target.get_by_role("button", name=re.compile(r"저장")),
            target.locator("button.save_btn__"),
            target.locator("button[data-click-area='tpb.save']"),
            target.get_by_role("button", name="임시저장"),
        ):
            if btn.count() > 0:
                btn.first.click(timeout=5000)
                time.sleep(2.5)
                return
    raise RuntimeError("저장 버튼을 찾지 못했습니다.")


def publish_live(page: Page, *, root: EditorRoot | None = None) -> None:
    log("발행 클릭…")
    targets = [page]
    if root is not None and root is not page:
        targets.append(root)
    for target in targets:
        btn = target.get_by_role("button", name="발행")
        if btn.count() > 0:
            btn.first.click(timeout=5000)
            time.sleep(1)
            if btn.count() > 1:
                btn.last.click()
            time.sleep(3)
            return
    raise RuntimeError("발행 버튼을 찾지 못했습니다.")


def save_debug(page: Page, name: str) -> None:
    from naver_auto.publish.playwright_client import save_debug_screenshot

    save_debug_screenshot(page, name)
