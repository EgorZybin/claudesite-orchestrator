from __future__ import annotations

from datetime import datetime

from app.db.models.job_run import JobRun
from app.db.models.manual_review import ManualReviewQueue


def _dt(v: datetime | None) -> str | None:
    if v is None:
        return None
    return v.isoformat(sep=" ", timespec="seconds")


def job_run_to_dict(job: JobRun) -> dict[str, object]:
    return {
        "id": job.id,
        "site_id": job.site_id,
        "celery_task_id": job.celery_task_id,
        "task_type": job.task_type.value,
        "status": job.status.value,
        "input_params": job.input_params,
        "page_ids": job.page_ids,
        "iteration_count": job.iteration_count,
        "turgenev_score": job.turgenev_score,
        "summary": job.summary,
        "tech_log": job.tech_log,
        "started_at": _dt(job.started_at),
        "finished_at": _dt(job.finished_at),
    }


def manual_review_to_dict(row: ManualReviewQueue, *, page_slug: str | None = None) -> dict[str, object]:
    return {
        "id": row.id,
        "site_id": row.site_id,
        "page_id": row.page_id,
        "page_slug": page_slug,
        "job_run_id": row.job_run_id,
        "status": row.status.value,
        "last_turgenev_score": row.last_turgenev_score,
        "turgenev_remarks": row.turgenev_remarks,
        "last_revision_id": row.last_revision_id,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }
