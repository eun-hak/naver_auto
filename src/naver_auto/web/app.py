"""naver-auto 웹 대시보드 API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from naver_auto.paths import PROJECT_ROOT, ensure_dirs
from naver_auto.web import services
from naver_auto.web.jobs import job_manager

STATIC_DIR = PROJECT_ROOT / "web" / "static"

app = FastAPI(title="naver-auto", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateBody(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    category: str | None = None
    skip_polish: bool = False


class FetchImagesBody(BaseModel):
    force: bool = True


class PublishBody(BaseModel):
    live: bool = False
    refresh_images: bool = False


@app.on_event("startup")
def _startup() -> None:
    ensure_dirs()


@app.get("/api/status")
def api_status():
    return services.pipeline_status()


@app.get("/api/drafts")
def api_list_drafts(status: str | None = Query(None)):
    return {"drafts": services.list_drafts(status=status or None)}


@app.get("/api/drafts/{draft_id}")
def api_draft_detail(draft_id: str):
    try:
        return services.draft_detail(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/drafts/{draft_id}/images/{filename}")
def api_draft_image(draft_id: str, filename: str):
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "invalid filename")
    try:
        draft_dir = services.find_draft_dir(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    path = draft_dir / "images" / filename
    if not path.exists():
        raise HTTPException(404, "image not found")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/drafts/create")
def api_create(body: CreateBody):
    keyword = body.keyword.strip()
    if not keyword:
        raise HTTPException(400, "키워드 필요")

    def task(job):
        return services.run_create(
            job,
            keyword=keyword,
            category=body.category,
            skip_polish=body.skip_polish,
        )

    job = job_manager.submit("create", task, message=f"초안 생성: {keyword}")
    return {"job_id": job.id}


@app.post("/api/drafts/{draft_id}/fetch-images")
def api_fetch_images(draft_id: str, body: FetchImagesBody):
    try:
        services.find_draft_dir(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    def task(job):
        return services.run_fetch_images(job, draft_id, force=body.force)

    job = job_manager.submit("fetch-images", task, message="이미지 수집")
    return {"job_id": job.id}


@app.post("/api/drafts/{draft_id}/publish")
def api_publish(draft_id: str, body: PublishBody):
    try:
        services.find_draft_dir(draft_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc

    def task(job):
        return services.run_publish(
            job,
            draft_id,
            live=body.live,
            refresh_images=body.refresh_images,
        )

    job = job_manager.submit("publish", task, message="네이버 업로드")
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.to_dict()


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
