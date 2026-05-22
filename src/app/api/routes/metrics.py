from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import readonly_session
from app.db.models.enums import JobRunStatus, ManualReviewStatus
from app.db.models.job_run import JobRun
from app.db.models.manual_review import ManualReviewQueue

router = APIRouter(tags=["monitoring"])


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(session: Session = Depends(readonly_session)) -> str:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)

    failed_24h = session.scalar(
        select(func.count())
        .select_from(JobRun)
        .where(
            JobRun.status == JobRunStatus.FAILED,
            JobRun.finished_at.is_not(None),
            JobRun.finished_at >= cutoff,
        ),
    ) or 0

    success_24h = session.scalar(
        select(func.count())
        .select_from(JobRun)
        .where(
            JobRun.status == JobRunStatus.SUCCESS,
            JobRun.finished_at.is_not(None),
            JobRun.finished_at >= cutoff,
        ),
    ) or 0

    manual_pending = session.scalar(
        select(func.count())
        .select_from(ManualReviewQueue)
        .where(ManualReviewQueue.status == ManualReviewStatus.PENDING),
    ) or 0

    lines = [
        "# HELP claudesite_jobs_failed_last_24h job_runs with status failed (finished in window)",
        "# TYPE claudesite_jobs_failed_last_24h gauge",
        f"claudesite_jobs_failed_last_24h {failed_24h}",
        "# HELP claudesite_jobs_success_last_24h job_runs with status success (finished in window)",
        "# TYPE claudesite_jobs_success_last_24h gauge",
        f"claudesite_jobs_success_last_24h {success_24h}",
        "# HELP claudesite_manual_review_pending_rows manual_review_queue rows with pending status",
        "# TYPE claudesite_manual_review_pending_rows gauge",
        f"claudesite_manual_review_pending_rows {manual_pending}",
    ]
    lines.append("")
    return "\n".join(lines)
