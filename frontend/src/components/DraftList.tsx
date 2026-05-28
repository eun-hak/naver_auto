import type { DraftSummary } from "../types";

const STATUS_LABEL: Record<string, string> = {
  review: "검토",
  draft_ready: "준비",
  ready_to_publish: "발행대기",
  naver_draft: "임시저장됨",
  published: "발행됨",
};

interface Props {
  drafts: DraftSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function DraftList({ drafts, selectedId, onSelect }: Props) {
  if (!drafts.length) {
    return (
      <p className="empty">초안이 없습니다. 왼쪽에서 새 글을 만들어 보세요.</p>
    );
  }

  return (
    <div className="draft-list">
      {drafts.map((d) => (
        <button
          key={d.draft_id}
          type="button"
          className={`draft-card ${d.draft_id === selectedId ? "selected" : ""}`}
          onClick={() => onSelect(d.draft_id)}
        >
          <h3>{d.title || d.keyword}</h3>
          <div className="row">
            <span className="status-pill">
              {STATUS_LABEL[d.status] ?? d.status}
            </span>
            <span>{d.char_count.toLocaleString()}자</span>
            <span>이미지 {d.image_count}장</span>
            <span>{d.keyword}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
