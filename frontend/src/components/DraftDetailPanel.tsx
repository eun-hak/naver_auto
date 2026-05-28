import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { DraftDetail } from "../types";

type Tab = "body" | "images" | "plan";

function slotNumber(img: { name: string; slot: string }): number {
  const fromSlot = parseInt(img.slot, 10);
  if (!Number.isNaN(fromSlot)) return fromSlot;
  const fromName = parseInt(img.name.replace(/\D/g, ""), 10);
  return Number.isNaN(fromName) ? 0 : fromName;
}

interface Props {
  detail: DraftDetail;
  onFetchImages: (keepSlots: number[]) => void;
  onPublish: (refreshImages: boolean) => void;
}

export function DraftDetailPanel({
  detail,
  onFetchImages,
  onPublish,
}: Props) {
  const [tab, setTab] = useState<Tab>("body");
  const [refreshImages, setRefreshImages] = useState(false);
  const [keepSlots, setKeepSlots] = useState<Set<number>>(new Set());

  const meta = detail.meta as {
    title?: string;
    status?: string;
    char_count?: number;
  };

  const plannedSlots = useMemo(() => {
    const fromPlan = (detail.image_plan ?? [])
      .map((p) => Number(p.slot))
      .filter((n) => n > 0);
    if (fromPlan.length) {
      return [...new Set(fromPlan)].sort((a, b) => a - b);
    }
    const fromBody = [...detail.body.matchAll(/images\/(\d+)\.jpg/g)]
      .map((m) => parseInt(m[1], 10))
      .filter((n) => n > 0);
    if (fromBody.length) {
      return [...new Set(fromBody)].sort((a, b) => a - b);
    }
    return detail.images
      .map(slotNumber)
      .filter((n) => n > 0)
      .sort((a, b) => a - b);
  }, [detail.image_plan, detail.body, detail.images]);

  const hasImages = detail.images.length > 0;

  const imageVersion =
    detail.images_version ||
    (typeof detail.meta.images_version === "number"
      ? detail.meta.images_version
      : 0);

  useEffect(() => {
    if (hasImages) {
      setKeepSlots(
        new Set(detail.images.map(slotNumber).filter((n) => n > 0)),
      );
    } else {
      setKeepSlots(new Set());
    }
  }, [detail.draft_id, hasImages, detail.images]);

  const refetchCount = hasImages
    ? plannedSlots.filter((s) => !keepSlots.has(s)).length
    : plannedSlots.length;

  const toggleKeep = (slot: number) => {
    setKeepSlots((prev) => {
      const next = new Set(prev);
      if (next.has(slot)) next.delete(slot);
      else next.add(slot);
      return next;
    });
  };

  const handleRefetch = () => {
    if (refetchCount === 0) {
      alert(
        "재수집할 이미지가 없습니다.\n유지하지 않을 이미지의 '유지' 체크를 해제한 뒤 재수집하세요.",
      );
      return;
    }
    onFetchImages(hasImages ? [...keepSlots].sort((a, b) => a - b) : []);
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
            onClick={handleRefetch}
            disabled={!plannedSlots.length}
          >
            {hasImages ? "이미지 재수집" : "이미지 수집"}
            {refetchCount > 0 ? ` (${refetchCount}장)` : ""}
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
        <>
          <p className="image-hint">
            체크된 이미지는 <strong>유지</strong>, 체크 해제한 슬롯만 재수집됩니다.
          </p>
          <div className="image-grid">
            {detail.images.length ? (
              detail.images.map((img) => {
                const slot = slotNumber(img);
                const kept = keepSlots.has(slot);
                const v = imageVersion || img.mtime || 0;
                return (
                  <figure
                    key={img.name}
                    className={`image-card ${kept ? "kept" : "refetch"}`}
                  >
                    <button
                      type="button"
                      className="image-card-btn"
                      onClick={() => toggleKeep(slot)}
                      title={kept ? "유지 — 클릭 시 재수집 대상" : "재수집 예정 — 클릭 시 유지"}
                    >
                      <img
                        src={api.imageUrl(detail.draft_id, img.name, v)}
                        alt={img.name}
                        loading="lazy"
                      />
                      <span className={`image-badge ${kept ? "keep" : "new"}`}>
                        {kept ? "유지" : "재수집"}
                      </span>
                    </button>
                    <figcaption>{img.name}</figcaption>
                  </figure>
                );
              })
            ) : (
              <p className="empty">
                {plannedSlots.length
                  ? `이미지 ${plannedSlots.length}슬롯 — 위 「이미지 수집」을 눌러 주세요.`
                  : "이미지 없음"}
              </p>
            )}
          </div>
        </>
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
