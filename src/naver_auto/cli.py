"""naver-auto CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from naver_auto.content.generator import create_draft_from_keyword
from naver_auto.image.resolver import resolve_draft_images
from naver_auto.paths import DRAFTS_DIR, ensure_dirs
from naver_auto.publish.daily_limit import can_publish, count_today, daily_limit
from naver_auto.publish.playwright_client import session_exists
from naver_auto.publish.uploader import publish_draft

app = typer.Typer(help="키워드 기반 네이버 블로그 자동 생성·임시저장")


def _find_draft(draft_id: str) -> Path:
    direct = DRAFTS_DIR / draft_id
    if direct.exists():
        return direct
    matches = list(DRAFTS_DIR.glob(f"*{draft_id}*"))
    if not matches:
        raise typer.BadParameter(f"초안 없음: {draft_id}")
    return matches[0]


@app.command("create")
def create(
    keyword: str = typer.Option(..., "--keyword", "-k", help="블로그 주제 키워드"),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="네이버 카테고리"),
    skip_polish: bool = typer.Option(False, "--skip-polish", help="도입부 polish 생략"),
) -> None:
    """키워드로 블로그 초안 생성."""
    ensure_dirs()
    typer.echo(f"[create] 키워드: {keyword}")
    out_dir = create_draft_from_keyword(keyword, category=category, skip_polish=skip_polish)
    resolve_draft_images(out_dir)
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    typer.echo(f"  → {out_dir}")
    typer.echo(f"  status={meta['status']}, {meta['char_count']}자")
    if meta.get("quality_errors"):
        typer.echo(f"  warnings: {', '.join(meta['quality_errors'])}")


@app.command("list")
def list_drafts(
    status: Optional[str] = typer.Option(None, "--status", help="상태 필터"),
) -> None:
    """저장된 초안 목록."""
    ensure_dirs()
    rows: list[tuple[str, str, str, int]] = []
    for path in sorted(DRAFTS_DIR.iterdir()):
        if not path.is_dir():
            continue
        meta_path = path / "meta.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        st = meta.get("status", "?")
        if status and st != status:
            continue
        rows.append(
            (
                meta.get("draft_id", path.name),
                meta.get("keyword", ""),
                st,
                meta.get("char_count", 0),
            )
        )

    if not rows:
        typer.echo("초안 없음.")
        return

    typer.echo(f"{'DRAFT_ID':<36} {'STATUS':<14} {'CHARS':>6}  KEYWORD")
    typer.echo("-" * 80)
    for draft_id, kw, st, chars in rows:
        typer.echo(f"{draft_id:<36} {st:<14} {chars:>6}  {kw[:30]}")


@app.command("status")
def status_cmd() -> None:
    """파이프라인 상태."""
    ensure_dirs()
    draft_n = sum(
        1
        for p in DRAFTS_DIR.iterdir()
        if p.is_dir() and (p / "body.md").exists()
    )
    ready = sum(
        1
        for p in DRAFTS_DIR.iterdir()
        if p.is_dir()
        and (p / "meta.json").exists()
        and json.loads((p / "meta.json").read_text()).get("status") == "draft_ready"
    )
    review = sum(
        1
        for p in DRAFTS_DIR.iterdir()
        if p.is_dir()
        and (p / "meta.json").exists()
        and json.loads((p / "meta.json").read_text()).get("status") == "review"
    )
    naver_draft = sum(
        1
        for p in DRAFTS_DIR.iterdir()
        if p.is_dir()
        and (p / "meta.json").exists()
        and json.loads((p / "meta.json").read_text()).get("status") == "naver_draft"
    )

    typer.echo("=== naver-auto 상태 ===")
    typer.echo(f"  초안 (drafts):       {draft_n}건")
    typer.echo(f"    draft_ready:       {ready}건")
    typer.echo(f"    review:            {review}건")
    typer.echo(f"    naver_draft:       {naver_draft}건")
    typer.echo(f"  오늘 발행/임시저장:  {count_today()}/{daily_limit()}건")
    typer.echo(f"  네이버 세션:         {'OK' if session_exists() else '없음 (login_once.py)'}")
    typer.echo(f"  drafts 경로:         {DRAFTS_DIR}")


@app.command("fetch-images")
def fetch_images_cmd(
    draft_id: str = typer.Option(..., "--draft-id", help="이미지 재수집할 초안 ID"),
    force: bool = typer.Option(False, "--force", help="기존 이미지 삭제 후 재수집"),
) -> None:
    """SNS·웹에서 관련 이미지 수집."""
    ensure_dirs()
    draft_dir = _find_draft(draft_id)
    typer.echo(f"[fetch-images] {draft_dir.name} …")
    paths = resolve_draft_images(draft_dir, force=force)
    meta = json.loads((draft_dir / "meta.json").read_text(encoding="utf-8"))
    sources = meta.get("image_sources", [])
    typer.echo(f"  → {len(paths)}장 저장")
    if sources:
        typer.echo(f"  sources: {', '.join(sources)}")


@app.command("publish")
def publish_cmd(
    draft_id: Optional[str] = typer.Option(None, "--draft-id", help="발행할 초안 ID"),
    all_: bool = typer.Option(False, "--all", help="draft_ready/review 초안 일괄 임시저장"),
    limit: Optional[int] = typer.Option(None, "--limit", help="일괄 처리 건수"),
    live: bool = typer.Option(False, "--live", help="즉시 발행 (기본: 임시저장)"),
) -> None:
    """네이버 블로그 임시저장 또는 발행."""
    ensure_dirs()

    if all_:
        targets: list[Path] = []
        for path in sorted(DRAFTS_DIR.iterdir()):
            if not path.is_dir() or not (path / "meta.json").exists():
                continue
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            if meta.get("status") in ("draft_ready", "review"):
                targets.append(path)
        if limit:
            targets = targets[:limit]
        if not targets:
            typer.echo("발행할 초안 없음.")
            raise typer.Exit(0)

        ok_count = 0
        for path in targets:
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            did = meta.get("draft_id", path.name)
            ok, msg = can_publish()
            if not ok:
                typer.echo(msg)
                break
            typer.echo(f"[publish] {did} …")
            try:
                publish_draft(did, live=live)
                ok_count += 1
            except Exception as exc:
                typer.echo(f"  실패: {exc}", err=True)
        typer.echo(f"완료: {ok_count}건")
        return

    if not draft_id:
        typer.echo("--draft-id 또는 --all 필요", err=True)
        raise typer.Exit(1)

    _find_draft(draft_id)
    typer.echo(f"[publish] {draft_id} ({'live' if live else 'draft'}) …")
    out = publish_draft(draft_id, live=live)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    typer.echo(f"  → status={meta['status']}")
    if meta.get("naver_url"):
        typer.echo(f"  url={meta['naver_url']}")


if __name__ == "__main__":
    app()
