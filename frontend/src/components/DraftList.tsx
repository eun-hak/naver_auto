import { useEffect, useMemo, useState } from "react";
import type { DraftSummary } from "../types";

const STATUS_LABEL: Record<string, string> = {
  review: "검토",
  draft_ready: "준비",
  ready_to_publish: "발행대기",
  naver_draft: "임시저장",
  published: "발행",
};

interface DateGroup {
  key: string;
  label: string;
  drafts: DraftSummary[];
}

function localDateKey(iso: string): string | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const d = new Date(t);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function formatDateLabel(key: string): string {
  if (key === "_unknown") return "날짜 없음";

  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(y, m - 1, d);
  target.setHours(0, 0, 0, 0);

  const diffDays = Math.round(
    (today.getTime() - target.getTime()) / (1000 * 60 * 60 * 24),
  );
  if (diffDays === 0) return "오늘";
  if (diffDays === 1) return "어제";

  const opts: Intl.DateTimeFormatOptions =
    y === today.getFullYear()
      ? { month: "long", day: "numeric", weekday: "short" }
      : { year: "numeric", month: "long", day: "numeric", weekday: "short" };
  return date.toLocaleDateString("ko-KR", opts);
}

function formatTime(iso?: string): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function groupByDate(drafts: DraftSummary[]): DateGroup[] {
  const sorted = [...drafts].sort((a, b) => {
    const ta = a.generated_at ? Date.parse(a.generated_at) : 0;
    const tb = b.generated_at ? Date.parse(b.generated_at) : 0;
    return tb - ta;
  });

  const map = new Map<string, DraftSummary[]>();
  for (const draft of sorted) {
    const key =
      (draft.generated_at && localDateKey(draft.generated_at)) || "_unknown";
    const list = map.get(key) ?? [];
    list.push(draft);
    map.set(key, list);
  }

  return [...map.entries()].map(([key, items]) => ({
    key,
    label: formatDateLabel(key),
    drafts: items,
  }));
}

function groupKeyForDraft(groups: DateGroup[], draftId: string): string | null {
  for (const g of groups) {
    if (g.drafts.some((d) => d.draft_id === draftId)) return g.key;
  }
  return null;
}

interface Props {
  drafts: DraftSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function DraftList({ drafts, selectedId, onSelect }: Props) {
  const groups = useMemo(() => groupByDate(drafts), [drafts]);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (groups.length && next.size === 0) {
        next.add(groups[0].key);
      }
      if (selectedId) {
        const key = groupKeyForDraft(groups, selectedId);
        if (key) next.add(key);
      }
      return next;
    });
  }, [groups, selectedId]);

  const toggleGroup = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

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
    <div className="draft-list-wrap">
      {groups.map((group) => {
        const isOpen = expanded.has(group.key);
        return (
          <section
            key={group.key}
            className={`draft-date-group ${isOpen ? "open" : "closed"}`}
          >
            <button
              type="button"
              className="draft-date-toggle"
              onClick={() => toggleGroup(group.key)}
              aria-expanded={isOpen}
            >
              <span className="draft-date-chevron" aria-hidden>
                ▸
              </span>
              <span className="draft-date-label-text">{group.label}</span>
              <span className="draft-date-count">{group.drafts.length}</span>
            </button>
            {isOpen && (
              <ul className="draft-list">
                {group.drafts.map((d) => {
                  const selected = d.draft_id === selectedId;
                  const time = formatTime(d.generated_at);
                  return (
                    <li key={d.draft_id}>
                      <button
                        type="button"
                        className={`draft-row ${selected ? "selected" : ""}`}
                        onClick={() => onSelect(d.draft_id)}
                        title={d.title || d.keyword}
                      >
                        <span className="draft-row-title">
                          {d.title || d.keyword}
                        </span>
                        <span className="draft-row-meta">
                          {time && <span>{time}</span>}
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
            )}
          </section>
        );
      })}
    </div>
  );
}
