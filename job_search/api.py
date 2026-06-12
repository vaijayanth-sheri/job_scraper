from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from job_search.scraper import (
    RUNTIME_SEARCH_DIR,
    SUPPORTED_JOBSPY_SOURCES,
    SearchMetadata,
    build_search_params,
    dataframe_to_records,
    run_search,
)


FRONTEND_DIST = Path("frontend") / "dist"
DEFAULT_SOURCES = ["linkedin", "indeed"]
MAX_WORKERS = 2


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class SearchCreateRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=120)
    sources: list[str] = Field(default_factory=lambda: DEFAULT_SOURCES.copy())
    results_per_source: int = Field(default=25, ge=1, le=100)
    distance_km: int = Field(default=50, ge=0, le=200)
    hours_old: int | None = Field(default=None, ge=1, le=720)

    @field_validator("keyword", "location")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank.")
        return stripped

    @field_validator("sources")
    @classmethod
    def normalize_sources(cls, value: list[str]) -> list[str]:
        normalized = [source.strip().lower() for source in value if source.strip()]
        if not normalized:
            raise ValueError("Select at least one job board.")
        return normalized


class SearchCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class SearchStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    request: dict[str, Any]
    metadata: dict[str, Any] | None = None
    error: str | None = None


class SearchResultsResponse(BaseModel):
    job_id: str
    rows: list[dict[str, Any]]
    metadata: dict[str, Any]


class SearchJob:
    def __init__(self, job_id: str, request: SearchCreateRequest) -> None:
        now = utc_now()
        self.job_id = job_id
        self.status = JobStatus.queued
        self.created_at = now
        self.updated_at = now
        self.request = request
        self.metadata: SearchMetadata | None = None
        self.rows: list[dict[str, Any]] = []
        self.csv_path: Path | None = None
        self.error: str | None = None

    def to_status_response(self) -> SearchStatusResponse:
        return SearchStatusResponse(
            job_id=self.job_id,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            request=self.request.model_dump(),
            metadata=metadata_to_dict(self.metadata) if self.metadata else None,
            error=self.error,
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def metadata_to_dict(metadata: SearchMetadata) -> dict[str, Any]:
    return asdict(metadata)


app = FastAPI(title="German Job Search Collector", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
jobs: dict[str, SearchJob] = {}
jobs_lock = threading.Lock()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/sources")
def sources() -> dict[str, list[dict[str, Any]]]:
    return {
        "sources": [
            {"id": "linkedin", "label": "LinkedIn", "available": True},
            {"id": "indeed", "label": "Indeed", "available": True},
            {
                "id": "stepstone",
                "label": "StepStone",
                "available": False,
                "reason": "JobSpy does not support StepStone yet.",
            },
        ]
    }


@app.post("/api/searches", response_model=SearchCreateResponse, status_code=202)
def create_search(request: SearchCreateRequest) -> SearchCreateResponse:
    try:
        build_search_params(
            keyword=request.keyword,
            location=request.location,
            sources=request.sources,
            results_per_source=request.results_per_source,
            distance_km=request.distance_km,
            hours_old=request.hours_old,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = uuid.uuid4().hex
    search_job = SearchJob(job_id=job_id, request=request)
    with jobs_lock:
        jobs[job_id] = search_job

    executor.submit(run_search_job, job_id)
    return SearchCreateResponse(job_id=job_id, status=JobStatus.queued)


@app.get("/api/searches/{job_id}", response_model=SearchStatusResponse)
def get_search(job_id: str) -> SearchStatusResponse:
    return get_job(job_id).to_status_response()


@app.get("/api/searches/{job_id}/results", response_model=SearchResultsResponse)
def get_search_results(job_id: str) -> SearchResultsResponse:
    search_job = get_job(job_id)
    if search_job.status not in {JobStatus.completed, JobStatus.failed}:
        raise HTTPException(status_code=409, detail="Search has not finished yet.")
    if search_job.metadata is None:
        raise HTTPException(status_code=404, detail="No results are available.")

    return SearchResultsResponse(
        job_id=job_id,
        rows=search_job.rows,
        metadata=metadata_to_dict(search_job.metadata),
    )


@app.get("/api/searches/{job_id}/csv")
def download_search_csv(job_id: str) -> FileResponse:
    search_job = get_job(job_id)
    if search_job.status != JobStatus.completed:
        raise HTTPException(status_code=409, detail="CSV is available after completion.")
    if search_job.csv_path is None or not search_job.csv_path.exists():
        raise HTTPException(status_code=404, detail="CSV file was not found.")

    return FileResponse(
        search_job.csv_path,
        media_type="text/csv",
        filename=search_job.csv_path.name,
    )


def get_job(job_id: str) -> SearchJob:
    with jobs_lock:
        search_job = jobs.get(job_id)
    if search_job is None:
        raise HTTPException(status_code=404, detail="Search job was not found.")
    return search_job


def run_search_job(job_id: str) -> None:
    search_job = get_job(job_id)
    update_job(job_id, status=JobStatus.running)

    try:
        request = search_job.request
        params = build_search_params(
            keyword=request.keyword,
            location=request.location,
            sources=request.sources,
            results_per_source=request.results_per_source,
            distance_km=request.distance_km,
            hours_old=request.hours_old,
        )
        result = run_search(
            params=params,
            output_dir=RUNTIME_SEARCH_DIR / job_id,
            filename_suffix=job_id[:8],
        )
        final_status = JobStatus.completed
        error = None
        if result.metadata.source_errors and result.metadata.final_count == 0:
            final_status = JobStatus.failed
            error = "All supported sources failed or returned no exportable results."

        update_job(
            job_id,
            status=final_status,
            metadata=result.metadata,
            rows=dataframe_to_records(result.jobs),
            csv_path=result.csv_path,
            error=error,
        )
    except Exception as exc:
        logging.exception("Search job %s failed", job_id)
        update_job(job_id, status=JobStatus.failed, error=str(exc))


def update_job(
    job_id: str,
    *,
    status: JobStatus,
    metadata: SearchMetadata | None = None,
    rows: list[dict[str, Any]] | None = None,
    csv_path: Path | None = None,
    error: str | None = None,
) -> None:
    with jobs_lock:
        search_job = jobs[job_id]
        search_job.status = status
        search_job.updated_at = utc_now()
        if metadata is not None:
            search_job.metadata = metadata
        if rows is not None:
            search_job.rows = rows
        if csv_path is not None:
            search_job.csv_path = csv_path
        if error is not None:
            search_job.error = error


if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )


@app.get("/{full_path:path}", response_model=None)
def serve_frontend(full_path: str) -> FileResponse | dict[str, str]:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists() and not full_path.startswith("api/"):
        return FileResponse(index_path)
    return {
        "message": "Frontend build not found. Run the React dev server or build frontend/dist."
    }
