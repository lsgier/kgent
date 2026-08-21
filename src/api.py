import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, status
from pydantic import BaseModel

import orchestrator

log = logging.getLogger(__name__)
app = FastAPI(title="kgent dedup service")

DATA_ROOT = Path(os.getenv("KGENT_DATA_ROOT", "/app/data"))

_run_lock = threading.Lock()
_jobs: dict[str, "JobResponse"] = {}


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunOverrides(BaseModel):
    sparql_endpoint: str | None = None
    sparql_update_endpoint: str | None = None
    dedup_graph: str | None = None
    cluster_k: int | None = None
    cluster_threshold: float | None = None
    cluster_name_similarity_penalty: float | None = None


class RunResultSummary(BaseModel):
    groups_found: int
    rule_based_groups: int
    llm_groups: int
    entities_covered: int
    dedup_graph: str


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    overrides: RunOverrides
    result: RunResultSummary | None = None
    error: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _execute_job(job_id: str, overrides: RunOverrides) -> None:
    job = _jobs[job_id]
    try:
        job.status = JobStatus.RUNNING
        job.started_at = _utcnow()

        job_dir = DATA_ROOT / "jobs" / job_id
        kwargs = overrides.model_dump(exclude_none=True)
        kwargs.update(
            audit_log_path=str(job_dir / "audit.jsonl"),
            sparql_log_path=str(job_dir / "sparql.jsonl"),
            llm_log_path=str(job_dir / "llm.jsonl"),
            persons_cache_path=str(job_dir / "persons_cache.jsonl"),
        )
        summary = orchestrator.run(**kwargs)

        job.result = RunResultSummary(**summary)
        job.status = JobStatus.SUCCEEDED
    except Exception as exc:
        log.exception("job %s failed", job_id)
        job.status = JobStatus.FAILED
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished_at = _utcnow()
        _run_lock.release()


@app.post("/runs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_run(overrides: RunOverrides, background_tasks: BackgroundTasks) -> JobResponse:
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                             detail="A dedup run is already in progress")
    job_id = str(uuid.uuid4())
    job = JobResponse(job_id=job_id, status=JobStatus.QUEUED, created_at=_utcnow(), overrides=overrides)
    _jobs[job_id] = job
    background_tasks.add_task(_execute_job, job_id, overrides)
    return job


@app.get("/runs/{job_id}", response_model=JobResponse)
def get_run(job_id: str) -> JobResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown job id")
    return job


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
