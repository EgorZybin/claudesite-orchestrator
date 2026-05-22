from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.integration_failure import IntegrationFailure


class IntegrationFailureRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        *,
        site_id: int | None,
        job_run_id: int | None,
        page_id: int | None,
        stage: str,
        provider: str,
        error_class: str,
        message: str,
        detail_json: dict | list | None = None,
        retry_count: int = 0,
    ) -> IntegrationFailure:
        row = IntegrationFailure(
            site_id=site_id,
            job_run_id=job_run_id,
            page_id=page_id,
            stage=stage,
            provider=provider,
            error_class=error_class,
            message=message,
            detail_json=detail_json,
            retry_count=retry_count,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def list_for_site(self, site_id: int, *, limit: int = 200) -> list[IntegrationFailure]:
        q = (
            select(IntegrationFailure)
            .where(IntegrationFailure.site_id == site_id)
            .order_by(IntegrationFailure.created_at.desc())
            .limit(limit)
        )
        return list(self._s.scalars(q).all())
