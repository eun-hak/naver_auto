import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { DraftDetail, PipelineStatus } from "../types";

type Tab = "body" | "images" | "plan";

function slotNumber(img: { name: string; slot: string }): number {
  const fromSlot = parseInt(img.slot, 10);
  if (!Number.isNaN(fromSlot)) return fromSlot;
  const fromName = parseInt(img.name.replace(/\D/g, ""), 10);
  return Number.isNaN(fromName) ? 0 : fromName;
}

interface Props {
  detail: DraftDetail;
  status: PipelineStatus | null;
  onFetchImages: (
    keepSlots: number[],
    slotPrompts: Record<number, string>,
  ) => void;
  onPublish: (refreshImages: boolean) => void;
}

export function DraftDetailPanel({
  detail,
  status,
  onFetchImages,
  onPublish,
}: Props) {
  const [tab, setTab] = useState<Tab>("body");
  const [refreshImages, setRefreshImages] = useState(false);
  const [keepSlots, setKeepSlots] = useState<Set<number>>(new Set());
  const [slotPrompts, setSlotPrompts] = useState<Record<number, string>>({});

  const meta = detail.meta as {
    title?: string;
    status?: string;
    char_count?: number;
    slot_image_prompts?: Record<string, string>;
    slot_refetch_prompts?: Record<string, string>;
  };

  const savedSlotPrompts = meta.slot_image_prompts ?? {};

  const planBySlot = useMemo(() => {
    const map = new Map<number, { section?: string; prompt?: string }>();
    for (const p of detail.image_plan ?? []) {
      map.set(Number(p.slot), {
        section: p.section,
        prompt: p.gemini_prompt,
      });
    }
    return map;
  }, [detail.image_plan]);

  const imageErrors = useMemo(() => {
    const map = new Map<number, string>();
    const attrs = (detail.meta.image_attributions ?? []) as Array<{
      slot?: number;
      nvidia_error?: string;
    }>;
    for (const a of attrs) {
      if (a.slot != null && a.nvidia_error) {
        map.set(Number(a.slot), a.nvidia_error);
      }
    }
    return map;
  }, [detail.meta.image_attributions]);

  const generationErrors = Array.isArray(detail.meta.image_generation_errors)
    ? (detail.meta.image_generation_errors as string[])
    : [];

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
      const slots = detail.images.map(slotNumber).filter((n) => n > 0);
      setKeepSlots(new Set(slots.length ? slots : plannedSlots));
    } else {
      setKeepSlots(new Set());
    }
    const saved: Record<number, string> = {};
    const raw = meta.slot_refetch_prompts;
    if (raw && typeof raw === "object") {
      for (const [k, v] of Object.entries(raw)) {
        const n = parseInt(k, 10);
        if (!Number.isNaN(n) && v) saved[n] = String(v);
      }
    }
    setSlotPrompts(saved);
  }, [detail.draft_id, detail.images, hasImages, plannedSlots, meta.slot_refetch_prompts]);

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

  const setSlotPrompt = (slot: number, value: string) => {
    setSlotPrompts((prev) => ({ ...prev, [slot]: value }));
  };

  const handleRefetch = () => {
    if (!hasImages) {
      onFetchImages([], {});
      return;
    }
    if (refetchCount === 0) {
      alert(
        "재수집할 이미지를 선택해 주세요.\n「유지」 이미지를 클릭하면 재수집 대상이 됩니다.",
      );
      return;
    }
    const refetchSlots = plannedSlots.filter((s) => !keepSlots.has(s));
    const prompts: Record<number, string> = {};
    for (const slot of refetchSlots) {
      const text = (slotPrompts[slot] ?? "").trim();
      if (text) prompts[slot] = text;
    }
    onFetchImages([...keepSlots].sort((a, b) => a - b), prompts);
  };

  return (
    <section className="detail">
      <div className="detail-header">
        <div className="detail-title-block">
          <h2 className="detail-title">{meta.title || detail.draft_id}</h2>
          <p className="meta-line">
            {meta.status} · {meta.char_count ?? 0}자 · img{" "}
            {detail.images.length || plannedSlots.length}
          </p>
        </div>
        <div className="detail-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleRefetch}
            disabled={!plannedSlots.length || (hasImages && refetchCount === 0)}
          >
            {hasImages ? "이미지 재수집" : "이미지 수집"}
            {refetchCount > 0 ? ` (${refetchCount}장)` : ""}
          </button>
          <button
            type="button"
            className="btn btn-accent"
            onClick={() => onPublish(refreshImages)}
            disabled={status != null && !status.can_publish}
            title={
              status && !status.can_publish
                ? status.limit_message
                : status
                  ? `오늘 ${status.published_today}/${status.daily_limit}회 사용 (일 ${status.daily_limit}회 한도)`
                  : undefined
            }
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
          <p className="image-hint image-hint-compact">
            클릭: <strong>유지</strong> ↔ <strong>재수집</strong> · 비우면 AI 프롬프트
            {Object.keys(savedSlotPrompts).length > 0 && (
              <span className="image-hint-saved">
                {" "}
                · 생성 시 #{Object.keys(savedSlotPrompts).sort((a, b) => Number(a) - Number(b)).join(", #")} 지정
              </span>
            )}
          </p>
          {generationErrors.length > 0 && (
            <div className="image-error-banner" role="alert">
              <strong>이미지 생성 오류</strong>
              <ul>
                {generationErrors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="image-grid">
            {detail.images.length ? (
              detail.images.map((img) => {
                const slot = slotNumber(img);
                const kept = keepSlots.has(slot);
                const v = imageVersion || img.mtime || 0;
                const slotErr = imageErrors.get(slot);
                const plan = planBySlot.get(slot);
                return (
                  <figure
                    key={img.name}
                    className={`image-card ${kept ? "kept" : "refetch"}${slotErr ? " failed" : ""}`}
                  >
                    <button
                      type="button"
                      className="image-card-btn"
                      onClick={() => toggleKeep(slot)}
                      title={
                        kept
                          ? "유지 — 클릭 시 재수집 선택"
                          : "재수집 예정 — 클릭 시 유지"
                      }
                    >
                      <img
                        key={`${img.name}-${v}`}
                        src={api.imageUrl(detail.draft_id, img.name, v)}
                        alt={img.name}
                        loading="lazy"
                      />
                      <span className={`image-badge ${kept ? "keep" : "new"}`}>
                        {kept ? "유지" : "재수집"}
                      </span>
                    </button>
                    <figcaption>
                      {img.name}
                      {slotErr && (
                        <span className="image-slot-error" title={slotErr}>
                          ⚠{" "}
                          {slotErr.includes("필터") ? "필터 차단" : "생성 실패"}
                        </span>
                      )}
                    </figcaption>
                    {!kept && (
                      <label className="slot-prompt-label">
                        #{slot} 프롬프트
                        <textarea
                          className="slot-prompt-input"
                          value={slotPrompts[slot] ?? ""}
                          onChange={(e) => setSlotPrompt(slot, e.target.value)}
                          onClick={(e) => e.stopPropagation()}
                          placeholder={
                            plan?.prompt
                              ? `비우면 기본: ${plan.prompt.slice(0, 55)}…`
                              : "비우면 키워드 기반 AI 프롬프트"
                          }
                          rows={2}
                        />
                        <span className="field-hint">
                          짧게 적으면 Llama 8B가 FLUX용 영문으로 확장
                        </span>
                      </label>
                    )}
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
                  FLUX: {p.gemini_prompt}
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
