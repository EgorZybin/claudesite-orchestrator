from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.enums import ManualReviewStatus
from app.db.models.manual_review import ManualReviewQueue


class ManualReviewRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, queue_id: int) -> ManualReviewQueue | None:
        return self._s.get(ManualReviewQueue, queue_id)

    def list_pending(self, *, site_id: int | None = None) -> list[ManualReviewQueue]:
        q = select(ManualReviewQueue).where(ManualReviewQueue.status == ManualReviewStatus.PENDING)
        if site_id is not None:
            q = q.where(ManualReviewQueue.site_id == site_id)
        q = q.order_by(ManualReviewQueue.created_at.asc())
        return list(self._s.scalars(q).all())

    def create(
        self,
        *,
        site_id: int,
        page_id: int,
        job_run_id: int | None = None,
        status: ManualReviewStatus = ManualReviewStatus.PENDING,
        last_turgenev_score: float | None = None,
        turgenev_remarks: list | dict | None = None,
        last_revision_id: int | None = None,
    ) -> ManualReviewQueue:
        row = ManualReviewQueue(
            site_id=site_id,
            page_id=page_id,
            job_run_id=job_run_id,
            status=status,
            last_turgenev_score=last_turgenev_score,
            turgenev_remarks=turgenev_remarks,
            last_revision_id=last_revision_id,
        )
        self._s.add(row)
        self._s.flush()
        return row
