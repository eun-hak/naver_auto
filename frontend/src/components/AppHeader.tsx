import type { PipelineStatus } from "../types";

interface Props {
  status: PipelineStatus | null;
  draftCount: number;
  filter: string;
  onFilterChange: (value: string) => void;
  onNew: () => void;
  onRefresh: () => void;
}

export function AppHeader({
  status,
  draftCount,
  filter,
  onFilterChange,
  onNew,
  onRefresh,
}: Props) {
  return (
    <header className="app-header">
      <div className="app-header-left">
        <div className="brand brand-inline">
          <span className="brand-dot" />
          <strong>naver-auto</strong>
        </div>
        <div className="header-stats">
          <span title="초안 수">초안 {status?.drafts.total ?? draftCount}</span>
          <span
            title={
              status
                ? `오늘 네이버 업로드 ${status.published_today}/${status.daily_limit}회 (일 ${status.daily_limit}회 한도)`
                : "오늘 네이버 업로드"
            }
          >
            업로드 {status ? `${status.published_today}/${status.daily_limit}` : "-/30"}
          </span>
          <span
            className={`badge ${status?.session_ok ? "ok" : "no"}`}
            title={
              status
                ? `네이버 세션 · 업로드 ${status.browser_headless ? "headless" : "Chrome"}`
                : "네이버 세션"
            }
          >
            N {status ? (status.session_ok ? "OK" : "×") : "-"}
            {status?.browser_headless ? "·H" : ""}
          </span>
          <span
            className={`badge ${status?.gemini_ok ? "ok" : "no"}`}
            title="Gemini"
          >
            G {status ? (status.gemini_ok ? "OK" : "×") : "-"}
          </span>
        </div>
      </div>
      <div className="app-header-right">
        <select
          className="select select-sm"
          value={filter}
          onChange={(e) => onFilterChange(e.target.value)}
          aria-label="상태 필터"
        >
          <option value="">전체</option>
          <option value="review">검토</option>
          <option value="draft_ready">준비</option>
          <option value="ready_to_publish">발행대기</option>
          <option value="naver_draft">임시저장</option>
          <option value="published">발행됨</option>
        </select>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRefresh}>
          새로고침
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={onNew}>
          + 새 글
        </button>
      </div>
    </header>
  );
}
