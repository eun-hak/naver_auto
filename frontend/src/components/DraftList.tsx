import type { DraftSummary } from "../types";

const STATUS_LABEL: Record<string, string> = {
  review: "검토",
  draft_ready: "준비",
  ready_to_publish: "발행대기",
  naver_draft: "임시저장",
  published: "발행",
};

interface Props {
  drafts: DraftSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function DraftList({ drafts, selectedId, onSelect }: Props) {
  if (!drafts.length) {
    return (
      <p className="empty empty-compact">
        초안 없음
        <br />
        <span className="empty-sub">상단 「+ 새 글」으로 생성</span>
      </p>
    );
  }

  return (
    <ul className="draft-list">
      {drafts.map((d) => {
        const selected = d.draft_id === selectedId;
        return (
          <li key={d.draft_id}>
            <button
              type="button"
              className={`draft-row ${selected ? "selected" : ""}`}
              onClick={() => onSelect(d.draft_id)}
              title={d.title || d.keyword}
            >
              <span className="draft-row-title">{d.title || d.keyword}</span>
              <span className="draft-row-meta">
                <span className="status-pill">
                  {STATUS_LABEL[d.status] ?? d.status}
                </span>
                <span>{d.char_count.toLocaleString()}자</span>
                <span>{d.image_count}img</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
