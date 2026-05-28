export interface PipelineStatus {
  drafts: {
    total: number;
    draft_ready: number;
    review: number;
    naver_draft: number;
    published: number;
  };
  published_today: number;
  daily_limit: number;
  can_publish: boolean;
  limit_message: string;
  session_ok: boolean;
  gemini_ok: boolean;
  naver_api_ok: boolean;
  drafts_dir: string;
}

export interface DraftSummary {
  draft_id: string;
  keyword: string;
  title: string;
  status: string;
  char_count: number;
  image_count: number;
  generated_at?: string;
  published_at?: string;
  naver_url?: string;
}

export interface ImagePlanItem {
  slot: number;
  section?: string;
  search_query?: string;
  alt?: string;
  gemini_prompt?: string;
}

export interface DraftDetail {
  draft_id: string;
  meta: Record<string, unknown>;
  body: string;
  images: { name: string; slot: string }[];
  image_plan: ImagePlanItem[];
}

export interface Job {
  id: string;
  kind: string;
  status: "pending" | "running" | "success" | "error";
  message: string;
  logs: string[];
  result?: Record<string, unknown>;
  error?: string;
  created_at: string;
  finished_at?: string;
}
