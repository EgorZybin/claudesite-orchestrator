from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.job_event import JobEvent


class JobEventRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        *,
        site_id: int | None,
        job_run_id: int | None,
        celery_task_id: str | None,
        task_name: str,
        event_type: str,
        outcome: str | None = None,
        detail_json: dict | None = None,
    ) -> JobEvent:
        row = JobEvent(
            site_id=site_id,
            job_run_id=job_run_id,
            celery_task_id=celery_task_id,
            task_name=task_name,
            event_type=event_type,
            outcome=outcome,
            detail_json=detail_json,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def list_for_site(self, site_id: int, *, limit: int = 100) -> list[JobEvent]:
        q = (
            select(JobEvent)
            .where(JobEvent.site_id == site_id)
            .order_by(JobEvent.created_at.desc())
            .limit(limit)
        )
        return list(self._s.scalars(q).all())
