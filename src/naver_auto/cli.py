"""naver-auto CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from naver_auto.batch.keywords import ensure_queue_template, read_queue, run_keyword_batch
from naver_auto.content.generator import create_draft_from_keyword
from naver_auto.image.resolver import resolve_draft_images
from naver_auto.paths import DRAFTS_DIR, KEYWORDS_QUEUE_FILE, ensure_dirs, load_yaml
from naver_auto.publish.daily_limit import can_publish, count_today, daily_limit
from naver_auto.publish.playwright_client import browser_headless, session_exists
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
) -> None:
    """키워드로 블로그 초안 생성."""
    ensure_dirs()
    typer.echo(f"[create] 키워드: {keyword}")
    out_dir = create_draft_from_keyword(keyword, category=category)
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
    typer.echo(
        f"  업로드 브라우저:     {'headless (창 없음)' if browser_headless() else 'Chrome (창 표시)'}"
    )
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
    headless: bool = typer.Option(
        False,
        "--headless",
        help="Chrome 창 없이 업로드 (저장된 세션 필요, publish.yaml/NAVER_HEADLESS와 병용)",
    ),
) -> None:
    """네이버 블로그 임시저장 또는 발행."""
    ensure_dirs()

    if all_:
        targets: list[Path] = []
        for path in sorted(DRAFTS_DIR.iterdir()):
            if not path.is_dir() or not (path / "meta.json").exists():
                continue
            meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
            if meta.get("status") in ("draft_ready", "review", "ready_to_publish"):
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
                publish_draft(did, live=live, headless=headless or None)
                ok_count += 1
            except Exception as exc:
                typer.echo(f"  실패: {exc}", err=True)
        typer.echo(f"완료: {ok_count}건")
        return

    if not draft_id:
        typer.echo("--draft-id 또는 --all 필요", err=True)
        raise typer.Exit(1)

    _find_draft(draft_id)
    mode = "headless" if browser_headless(override=headless or None) else "Chrome"
    typer.echo(f"[publish] {draft_id} ({'live' if live else 'draft'}, {mode}) …")
    out = publish_draft(draft_id, live=live, headless=headless or None)
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    typer.echo(f"  → status={meta['status']}")
    if meta.get("naver_url"):
        typer.echo(f"  url={meta['naver_url']}")


@app.command("batch")
def batch_cmd(
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="키워드 txt (기본: data/keywords/queue.txt)",
    ),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="기본 카테고리 (줄별 | 카테고리 우선)"
    ),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="처리 건수 제한"),
    skip_images: bool = typer.Option(
        False, "--skip-images", help="FLUX 이미지 생성 생략"
    ),
    force: bool = typer.Option(
        False, "--force", help="같은 키워드 초안이 있어도 새로 생성"
    ),
    keep: bool = typer.Option(
        False, "--keep", help="성공해도 queue.txt에서 줄 제거하지 않음"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="실행 없이 대상 키워드만 출력"
    ),
    list_only: bool = typer.Option(
        False, "--list", help="queue.txt 키워드 목록만 출력"
    ),
    publish: bool = typer.Option(
        False,
        "--publish",
        "-p",
        help="초안 생성 후 네이버 임시저장 (Chrome)",
    ),
    live: bool = typer.Option(
        False, "--live", help="--publish 시 즉시 발행 (기본: 임시저장)"
    ),
    headless: bool = typer.Option(
        False,
        "--headless",
        help="--publish 시 Chrome 창 없이 업로드 (저장된 세션 필요)",
    ),
) -> None:
    """data/keywords/queue.txt 키워드 → 초안 일괄 생성 (--publish: 네이버까지)."""
    ensure_dirs()
    queue_path = file or ensure_queue_template()

    if list_only:
        items = read_queue(queue_path)
        if not items:
            typer.echo(f"대기 키워드 없음: {queue_path}")
            raise typer.Exit(0)
        typer.echo(f"queue: {queue_path} ({len(items)}건)")
        for i, item in enumerate(items, start=1):
            cat = f" | {item.category}" if item.category else ""
            typer.echo(f"  {i}. {item.keyword}{cat}")
        raise typer.Exit(0)

    cfg = load_yaml("publish.yaml")
    default_cat = category or cfg.get("default_category")

    typer.echo(f"[batch] {queue_path}")
    if publish:
        mode = "headless" if browser_headless(override=headless or None) else "Chrome"
        typer.echo(f"네이버 임시저장 포함 ({mode}, --live 시 즉시 발행)")
        typer.echo(f"  오늘 업로드: {count_today()}/{daily_limit()}건 (일 {daily_limit()}회 한도)")
    if dry_run:
        typer.echo("(dry-run — 생성하지 않음)")
    results = run_keyword_batch(
        queue_file=queue_path,
        default_category=default_cat,
        limit=limit,
        skip_images=skip_images,
        force=force,
        remove_on_success=not keep,
        dry_run=dry_run,
        publish=publish,
        live=live,
        headless=headless or None,
        on_progress=typer.echo,
    )

    if not results:
        typer.echo("처리할 키워드 없음. queue.txt에 한 줄씩 추가하세요.")
        typer.echo(f"  → {KEYWORDS_QUEUE_FILE}")
        raise typer.Exit(0)

    ok_n = sum(1 for r in results if r.ok)
    fail_n = len(results) - ok_n
    pub_n = sum(1 for r in results if r.published)
    typer.echo(f"\n완료: {ok_n}건 성공" + (f", {fail_n}건 실패" if fail_n else ""))
    if publish and pub_n:
        typer.echo(f"  네이버 저장: {pub_n}건")
    if fail_n:
        raise typer.Exit(1)


@app.command("scout")
def scout_cmd(
    limit: int = typer.Option(10, "--limit", "-n", help="queue.txt에 추가할 최대 키워드 수"),
    doc_limit: int = typer.Option(30_000, "--doc-limit", help="블로그 문서 수 상한 (초과 시 경쟁 과열로 제외)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="queue.txt에 저장하지 않고 결과만 출력"),
    skip_judge: bool = typer.Option(False, "--skip-judge", help="Gemini 적합성 심사 생략"),
) -> None:
    """실시간 트렌드에서 저경쟁 키워드 발굴 → queue.txt에 자동 추가."""
    from naver_auto.keyword.scout import run_keyword_scout

    ensure_dirs()
    report = run_keyword_scout(
        limit=limit,
        doc_limit=doc_limit,
        dry_run=dry_run,
        skip_judge=skip_judge,
        on_progress=typer.echo,
    )

    if report.rejected:
        typer.echo("\n심사 탈락:")
        for r in report.rejected:
            typer.echo(f"  ✗ {r['keyword']} — {r['reason']}")

    if not report.survivors:
        typer.echo("\n추가할 키워드 없음.")
        raise typer.Exit(0)

    header = "queue.txt 추가 예정 (dry-run)" if dry_run else "queue.txt 추가됨"
    typer.echo(f"\n{header}:")
    for r in report.survivors:
        typer.echo(f"  {r['keyword']}  (문서 {r['docs']:,}건)")
    typer.echo(f"\n→ {KEYWORDS_QUEUE_FILE}")


@app.command("ui")
def ui_cmd(
    port: int = typer.Option(8787, "--port", "-p", help="웹 UI 포트"),
    dev: bool = typer.Option(False, "--dev", help="빌드 생략 (frontend npm run dev 와 병행)"),
) -> None:
    """웹 대시보드 — React + FastAPI (http://127.0.0.1:8787)."""
    import subprocess
    import uvicorn

    from naver_auto.paths import PROJECT_ROOT
    from naver_auto.web.app import app as web_app

    static = PROJECT_ROOT / "web" / "static" / "index.html"
    frontend = PROJECT_ROOT / "frontend"
    if not dev and not static.exists():
        typer.echo("React 빌드 중…")
        subprocess.run(["npm", "install"], cwd=frontend, check=True)
        subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)

    typer.echo(f"naver-auto UI → http://127.0.0.1:{port}")
    if dev:
        typer.echo("개발: cd frontend && npm run dev  (http://127.0.0.1:5173)")
    uvicorn.run(web_app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    app()
