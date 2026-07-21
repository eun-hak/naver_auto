"""트렌드 키워드 자동 수집 — 트렌드 → 자동완성 확장 → 문서수 필터 → Gemini 심사 → queue.txt."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from naver_auto.keyword.analyzer import fetch_autocomplete, fetch_blog_total_count
from naver_auto.paths import KEYWORDS_DONE_LOG, KEYWORDS_QUEUE_FILE, USER_AGENT

GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=KR"
SIGNAL_REALTIME_URL = "https://api.signal.bz/news/realtime"
DEFAULT_DOC_LIMIT = 30_000  # 블로그 문서 수 상한 — 초과 시 경쟁 과열로 제외
DEFAULT_MAX_SEEDS = 20
DEFAULT_MAX_JUDGE = 40


@dataclass
class ScoutReport:
    seeds: list[str] = field(default_factory=list)
    candidates: int = 0
    survivors: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    added: list[str] = field(default_factory=list)


def _headers() -> dict[str, str]:
    return {"User-Agent": USER_AGENT}


def collect_google_trends() -> list[str]:
    r = httpx.get(GOOGLE_TRENDS_RSS, headers=_headers(), timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    return [
        t.text.strip()
        for t in root.iter("title")
        if t.text and t.text.strip() != "Daily Search Trends"
    ]


def collect_signal_realtime() -> list[str]:
    r = httpx.get(SIGNAL_REALTIME_URL, headers=_headers(), timeout=15)
    r.raise_for_status()
    return [str(it.get("keyword", "")).strip() for it in r.json().get("top10", [])]


def collect_trend_seeds(log: Callable[[str], None]) -> list[str]:
    seeds: list[str] = []
    for name, fetch in (("구글 트렌드", collect_google_trends), ("시그널 실검", collect_signal_realtime)):
        try:
            items = fetch()
            log(f"  {name}: {len(items)}개")
            seeds.extend(items)
        except Exception as exc:
            log(f"  {name} 실패: {type(exc).__name__}")
    return list(dict.fromkeys(s for s in seeds if s))


def _already_used() -> set[str]:
    used: set[str] = set()
    if KEYWORDS_DONE_LOG.exists():
        for line in KEYWORDS_DONE_LOG.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                used.add(parts[1].strip())
    if KEYWORDS_QUEUE_FILE.exists():
        for line in KEYWORDS_QUEUE_FILE.read_text(encoding="utf-8").splitlines():
            kw = line.split("|")[0].strip()
            if kw and not kw.startswith("#"):
                used.add(kw)
    return used


def _valid_candidate(keyword: str) -> bool:
    if not (2 <= len(keyword) <= 25):
        return False
    return bool(re.search(r"[가-힣]", keyword))


def _judge(survivors: list[dict]) -> list[dict]:
    """Gemini 일괄 심사 — 블로그 글감 적합성·유사중복만 판정."""
    from naver_auto.content.gemini_client import _generate, parse_json_object

    listing = "\n".join(
        f"- {r['keyword']} (블로그 문서 {r['docs']:,}건)" for r in survivors
    )
    prompt = f"""네이버 블로그 글감 후보를 심사해줘. 각 키워드에 대해:
- ok: 블로그 정보성 글로 쓸 만하면 true. 다음은 false — 의미 불명, 단순 인물명, 속보성(하루살이 이슈), 성인·의료·금융·정치처럼 저품질/명예훼손 위험 주제
- reason: 한 줄 근거
유사·중복 키워드(같은 주제의 변형)는 대표 1개만 ok로 하고 나머지는 false(reason에 '중복').

후보:
{listing}

JSON만 출력: {{"results": [{{"keyword": "...", "ok": true, "reason": "..."}}]}}"""
    text = _generate(prompt, system="너는 한국어 블로그 SEO 키워드 심사 전문가야.", temperature=0.2)
    return parse_json_object(text).get("results", [])


def run_keyword_scout(
    *,
    limit: int = 10,
    doc_limit: int = DEFAULT_DOC_LIMIT,
    dry_run: bool = False,
    skip_judge: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> ScoutReport:
    log = on_progress or (lambda _msg: None)
    report = ScoutReport()

    log("[scout] 트렌드 수집…")
    report.seeds = collect_trend_seeds(log)[:DEFAULT_MAX_SEEDS]
    if not report.seeds:
        log("[scout] 수집된 트렌드 없음")
        return report

    log("[scout] 자동완성 확장…")
    candidates: list[str] = []
    for seed in report.seeds:
        candidates.append(seed)
        try:
            candidates.extend(fetch_autocomplete(seed)[:6])
        except Exception:
            pass
        time.sleep(0.3)
    used = _already_used()
    candidates = [
        k for k in dict.fromkeys(candidates) if _valid_candidate(k) and k not in used
    ]
    report.candidates = len(candidates)
    log(f"[scout] 후보 {len(candidates)}개 (중복 제거 후)")

    log(f"[scout] 블로그 문서 수 필터 (상한 {doc_limit:,}건)…")
    survivors: list[dict] = []
    for kw in candidates:
        try:
            docs = fetch_blog_total_count(kw)
        except Exception:
            continue
        if 0 < docs <= doc_limit:
            survivors.append({"keyword": kw, "docs": docs})
        time.sleep(0.15)
    survivors.sort(key=lambda r: r["docs"])
    survivors = survivors[:DEFAULT_MAX_JUDGE]
    log(f"[scout] 필터 통과 {len(survivors)}개")

    if survivors and not skip_judge:
        log("[scout] Gemini 심사…")
        try:
            results = _judge(survivors)
            docs_by_kw = {r["keyword"]: r["docs"] for r in survivors}
            passed, rejected = [], []
            for r in results:
                kw = str(r.get("keyword", "")).strip()
                if kw not in docs_by_kw:
                    continue
                row = {"keyword": kw, "docs": docs_by_kw[kw], "reason": str(r.get("reason", ""))}
                (passed if r.get("ok") else rejected).append(row)
            report.rejected = rejected
            survivors = passed
        except Exception as exc:
            log(f"[scout] 심사 실패({type(exc).__name__}) — 필터 통과분 그대로 사용")

    report.survivors = survivors[:limit]

    if dry_run:
        return report

    if report.survivors:
        lines = "".join(f"{r['keyword']}\n" for r in report.survivors)
        if KEYWORDS_QUEUE_FILE.exists():
            tail = KEYWORDS_QUEUE_FILE.read_text(encoding="utf-8")
            if tail and not tail.endswith("\n"):
                lines = "\n" + lines
        with KEYWORDS_QUEUE_FILE.open("a", encoding="utf-8") as f:
            f.write(lines)
        report.added = [r["keyword"] for r in report.survivors]
        log(f"[scout] queue.txt에 {len(report.added)}개 추가")
    return report
