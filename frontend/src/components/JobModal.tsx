import type { Job } from "../types";

interface Props {
  job: Job;
  onClose: () => void;
}

export function JobModal({ job, onClose }: Props) {
  const done = job.status === "success" || job.status === "error";
  const title =
    job.status === "success"
      ? "완료"
      : job.status === "error"
        ? "오류"
        : "작업 진행 중…";

  return (
    <div className="modal-backdrop">
      <div className="modal modal-wide">
        <div className="job-header">
          <h3>{title}</h3>
          <span className={`badge ${job.status}`}>{job.status}</span>
        </div>
        <pre className="job-logs">
          {job.logs.join("\n") || job.message}
          {job.error ? `\n\n${job.error}` : ""}
        </pre>
        <div className="modal-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={onClose}
            disabled={!done}
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
