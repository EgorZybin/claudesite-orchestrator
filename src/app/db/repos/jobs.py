from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.enums import JobRunStatus, JobTaskType
from app.db.models.job_run import JobRun


class JobRunRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, job_id: int) -> JobRun | None:
        return self._s.get(JobRun, job_id)

    def get_by_celery_task_id(self, celery_task_id: str) -> JobRun | None:
        q = select(JobRun).where(JobRun.celery_task_id == celery_task_id).limit(1)
        return self._s.scalar(q)

    def create(
        self,
        *,
        site_id: int,
        task_type: JobTaskType,
        status: JobRunStatus = JobRunStatus.PENDING,
        celery_task_id: str | None = None,
        input_params: dict | None = None,
        page_ids: list[int] | None = None,
        started_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> JobRun:
        row = JobRun(
            site_id=site_id,
            task_type=task_type,
            status=status,
            celery_task_id=celery_task_id,
            input_params=input_params,
            page_ids=page_ids,
            started_at=started_at,
            idempotency_key=idempotency_key,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def append_tech_step(self, job: JobRun, step: str, detail: dict | None = None) -> None:
        log = dict(job.tech_log or {})
        steps = list(log.get("steps", []))

        steps.append(
            {
                "step": step,
                "ts": datetime.now(UTC).isoformat(),
                "detail": detail or {},
            }
        )
        log["steps"] = steps
        job.tech_log = log
