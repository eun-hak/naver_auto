"""백그라운드 작업 큐 (create / fetch-images / publish)."""

from __future__ import annotations

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class Job:
    id: str
    kind: str
    status: JobStatus = JobStatus.PENDING
    message: str = ""
    logs: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: _now())
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status.value,
            "message": self.message,
            "logs": self.logs[-80:],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self, *, max_workers: int = 2) -> None:
        self._jobs: dict[str, Job] = {}
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="naver-job")

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def submit(self, kind: str, fn: Callable[[Job], Any], *, message: str = "") -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, message=message)
        self._jobs[job.id] = job

        def runner() -> None:
            job.status = JobStatus.RUNNING
            try:
                result = fn(job)
                job.result = result if isinstance(result, dict) else {"value": result}
                job.status = JobStatus.SUCCESS
                job.message = job.message or "완료"
            except Exception as exc:
                job.status = JobStatus.ERROR
                job.error = str(exc)
                job.logs.append(traceback.format_exc())
                job.message = f"실패: {exc}"
            finally:
                job.finished_at = _now()

        self._pool.submit(runner)
        return job

    def log(self, job: Job, line: str) -> None:
        job.logs.append(line)


job_manager = JobManager()
