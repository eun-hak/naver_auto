import { useState } from "react";
import { api } from "../api";
import type { DraftDetail } from "../types";

type Tab = "body" | "images" | "plan";

interface Props {
  detail: DraftDetail;
  onFetchImages: () => void;
  onPublish: (refreshImages: boolean) => void;
}

export function DraftDetailPanel({
  detail,
  onFetchImages,
  onPublish,
}: Props) {
  const [tab, setTab] = useState<Tab>("body");
  const [refreshImages, setRefreshImages] = useState(false);
  const meta = detail.meta as {
    title?: string;
    status?: string;
    char_count?: number;
  };

  return (
    <section className="detail">
      <div className="detail-header">
        <div>
          <h2>{meta.title || detail.draft_id}</h2>
          <p className="meta-line">
            {detail.draft_id} · {meta.status} · {meta.char_count ?? 0}자
          </p>
        </div>
        <div className="detail-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onFetchImages}
          >
            이미지 재수집
          </button>
          <button
            type="button"
            className="btn btn-accent"
            onClick={() => onPublish(refreshImages)}
          >
            네이버 임시저장
          </button>
          <label className="check">
            <input
              type="checkbox"
              checked={refreshImages}
              onChange={(e) => setRefreshImages(e.target.checked)}
            />
            이미지 새로
          </label>
        </div>
      </div>

      <div className="tabs">
        {(["body", "images", "plan"] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            className={`tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
          >
            {t === "body" ? "본문" : t === "images" ? "이미지" : "이미지 계획"}
          </button>
        ))}
      </div>

      {tab === "body" && <pre className="body-pre">{detail.body}</pre>}

      {tab === "images" && (
        <div className="image-grid">
          {detail.images.length ? (
            detail.images.map((img) => (
              <figure key={img.name}>
                <img
                  src={api.imageUrl(detail.draft_id, img.name)}
                  alt={img.name}
                  loading="lazy"
                />
                <figcaption>{img.name}</figcaption>
              </figure>
            ))
          ) : (
            <p className="empty">이미지 없음</p>
          )}
        </div>
      )}

      {tab === "plan" && (
        <div className="plan-list">
          {detail.image_plan?.length ? (
            detail.image_plan.map((p) => (
              <div key={p.slot} className="plan-item">
                <strong>#{p.slot}</strong> {p.section}
                <div style={{ color: "var(--muted)", marginTop: "0.25rem" }}>
                  검색: {p.search_query}
                </div>
              </div>
            ))
          ) : (
            <p className="empty">image_plan 없음</p>
          )}
        </div>
      )}
    </section>
  );
}
