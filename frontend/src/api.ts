import type { DraftDetail, DraftSummary, Job, PipelineStatus } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail;
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => request<PipelineStatus>("/status"),
  listDrafts: (status?: string) =>
    request<{ drafts: DraftSummary[] }>(
      status ? `/drafts?status=${encodeURIComponent(status)}` : "/drafts",
    ),
  draftDetail: (id: string) =>
    request<DraftDetail>(`/drafts/${encodeURIComponent(id)}`),
  imageUrl: (draftId: string, filename: string, version?: number) => {
    const base = `/api/drafts/${encodeURIComponent(draftId)}/images/${encodeURIComponent(filename)}`;
    return version ? `${base}?v=${version}` : base;
  },
  createDraft: (body: {
    keyword: string;
    category: string | null;
    slot_prompts?: Record<string, string>;
  }) =>
    request<{ job_id: string }>("/drafts/create", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  fetchImages: (
    draftId: string,
    opts: {
      force?: boolean;
      keep_slots?: number[];
      slot_prompts?: Record<string, string>;
    } = {},
  ) =>
    request<{ job_id: string }>(
      `/drafts/${encodeURIComponent(draftId)}/fetch-images`,
      {
        method: "POST",
        body: JSON.stringify({
          force: opts.force ?? true,
          keep_slots: opts.keep_slots ?? null,
          slot_prompts: opts.slot_prompts ?? null,
        }),
      },
    ),
  publish: (
    draftId: string,
    opts: { live?: boolean; refresh_images?: boolean } = {},
  ) =>
    request<{ job_id: string }>(
      `/drafts/${encodeURIComponent(draftId)}/publish`,
      {
        method: "POST",
        body: JSON.stringify({
          live: opts.live ?? false,
          refresh_images: opts.refresh_images ?? false,
        }),
      },
    ),
  job: (jobId: string) => request<Job>(`/jobs/${jobId}`),
};

export function pollJob(
  jobId: string,
  onUpdate: (job: Job) => void,
): () => void {
  let stopped = false;
  const tick = async () => {
    if (stopped) return;
    try {
      const job = await api.job(jobId);
      onUpdate(job);
      if (job.status === "success" || job.status === "error") return;
    } catch {
      /* retry */
    }
    if (!stopped) setTimeout(tick, 1500);
  };
  tick();
  return () => {
    stopped = true;
  };
}
