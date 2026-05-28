import type { PipelineStatus } from "../types";

interface Props {
  status: PipelineStatus | null;
  onNew: () => void;
  onRefresh: () => void;
}

export function Sidebar({ status, onNew, onRefresh }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-dot" />
        <div>
          <strong>naver-auto</strong>
          <small>블로그 자동화</small>
        </div>
      </div>

      <section className="status-card">
        <p className="label">파이프라인</p>
        <div className="stat-row">
          <span>초안</span>
          <strong>{status?.drafts.total ?? "-"}</strong>
        </div>
        <div className="stat-row">
          <span>오늘 업로드</span>
          <strong>
            {status
              ? `${status.published_today} / ${status.daily_limit}`
              : "-"}
          </strong>
        </div>
        <div className="stat-row">
          <span>네이버 세션</span>
          <strong className={`badge ${status?.session_ok ? "ok" : "no"}`}>
            {status ? (status.session_ok ? "OK" : "없음") : "-"}
          </strong>
        </div>
        <div className="stat-row">
          <span>Gemini</span>
          <strong className={`badge ${status?.gemini_ok ? "ok" : "no"}`}>
            {status ? (status.gemini_ok ? "OK" : "없음") : "-"}
          </strong>
        </div>
      </section>

      <button type="button" className="btn btn-primary btn-block" onClick={onNew}>
        + 새 글 만들기
      </button>
      <button type="button" className="btn btn-ghost btn-block" onClick={onRefresh}>
        새로고침
      </button>
    </aside>
  );
}
