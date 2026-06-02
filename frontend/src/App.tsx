import { useCallback, useEffect, useRef, useState } from "react";
import { api, pollJob } from "./api";
import type { DraftDetail, DraftSummary, Job, PipelineStatus } from "./types";
import { CreateModal } from "./components/CreateModal";
import { AppHeader } from "./components/AppHeader";
import { DraftDetailEmpty } from "./components/DraftDetailEmpty";
import { DraftDetailPanel } from "./components/DraftDetailPanel";
import { DraftList } from "./components/DraftList";
import { JobModal } from "./components/JobModal";

export default function App() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DraftDetail | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [jobOpen, setJobOpen] = useState(false);
  const stopPollRef = useRef<(() => void) | null>(null);

  const refresh = useCallback(async () => {
    const [s, d] = await Promise.all([
      api.status(),
      api.listDrafts(filter || undefined),
    ]);
    setStatus(s);
    setDrafts(d.drafts);
  }, [filter]);

  const loadDetail = useCallback(async (id: string) => {
    setDetail(await api.draftDetail(id));
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
  }, [refresh]);

  useEffect(() => {
    if (!selectedId && drafts.length > 0) {
      setSelectedId(drafts[0].draft_id);
    }
  }, [drafts, selectedId]);

  useEffect(() => {
    if (selectedId) loadDetail(selectedId).catch(console.error);
    else setDetail(null);
  }, [selectedId, loadDetail]);

  useEffect(
    () => () => {
      stopPollRef.current?.();
    },
    [],
  );

  const startJob = (jobId: string) => {
    stopPollRef.current?.();
    setJob({
      id: jobId,
      kind: "",
      status: "running",
      message: "작업 중…",
      logs: [],
      created_at: "",
    });
    setJobOpen(true);
    stopPollRef.current = pollJob(jobId, (j) => {
      setJob(j);
      if (j.status === "success") {
        refresh();
        if (j.result?.draft_id) setSelectedId(String(j.result.draft_id));
        else if (selectedId) loadDetail(selectedId);
      }
      if (j.status === "error") refresh();
    });
  };

  const closeJob = () => {
    stopPollRef.current?.();
    stopPollRef.current = null;
    setJobOpen(false);
    setJob(null);
    refresh();
    if (selectedId) loadDetail(selectedId);
  };

  const handleCreate = async (payload: {
    keyword: string;
    category: string | null;
    slot_prompts: Record<number, string>;
  }) => {
    setShowCreate(false);
    const mapped: Record<string, string> = {};
    for (const [slot, prompt] of Object.entries(payload.slot_prompts)) {
      if (prompt.trim()) mapped[slot] = prompt.trim();
    }
    const { job_id } = await api.createDraft({
      keyword: payload.keyword,
      category: payload.category,
      slot_prompts: Object.keys(mapped).length ? mapped : undefined,
    });
    startJob(job_id);
  };

  const handleFetchImages = async (
    keepSlots: number[],
    slotPrompts: Record<number, string>,
  ) => {
    if (!selectedId) return;
    const mapped: Record<string, string> = {};
    for (const [slot, prompt] of Object.entries(slotPrompts)) {
      if (prompt.trim()) mapped[slot] = prompt.trim();
    }
    const { job_id } = await api.fetchImages(selectedId, {
      force: true,
      keep_slots: keepSlots,
      slot_prompts: Object.keys(mapped).length ? mapped : undefined,
    });
    startJob(job_id);
  };

  const handlePublish = async (refreshImages: boolean) => {
    if (!selectedId) return;
    if (!confirm("네이버에 업로드합니다. Chrome 창이 열립니다. 계속할까요?")) return;
    const { job_id } = await api.publish(selectedId, {
      refresh_images: refreshImages,
    });
    startJob(job_id);
  };

  return (
    <div className="app-shell">
      <AppHeader
        status={status}
        draftCount={drafts.length}
        filter={filter}
        onFilterChange={setFilter}
        onNew={() => setShowCreate(true)}
        onRefresh={() => refresh()}
      />

      <div className="workspace">
        <aside className="list-pane">
          <DraftList
            drafts={drafts}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </aside>

        <section className="detail-pane">
          {detail && selectedId ? (
            <DraftDetailPanel
              detail={detail}
              onFetchImages={handleFetchImages}
              onPublish={handlePublish}
            />
          ) : (
            <DraftDetailEmpty />
          )}
        </section>
      </div>

      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onSubmit={handleCreate} />
      )}

      {jobOpen && job && (
        <JobModal job={job} onClose={closeJob} />
      )}
    </div>
  );
}
