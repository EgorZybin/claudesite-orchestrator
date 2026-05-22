from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.form_submission import FormSubmission


class FormSubmissionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def create(
        self,
        *,
        site_id: int,
        page_id: int | None,
        page_slug: str | None,
        form_id: str,
        payload: dict[str, Any],
        status: str,
        ip: str | None,
        user_agent: str | None,
    ) -> FormSubmission:
        row = FormSubmission(
            site_id=site_id,
            page_id=page_id,
            page_slug=page_slug,
            form_id=form_id,
            payload=payload,
            status=status,
            ip=ip,
            user_agent=user_agent,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def get_by_id(self, sub_id: int) -> FormSubmission | None:
        return self._s.get(FormSubmission, sub_id)

    def list_for_site(
        self,
        *,
        site_id: int,
        status: str | None = None,
        form_id: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[FormSubmission]:
        q = select(FormSubmission).where(FormSubmission.site_id == site_id)
        if status:
            q = q.where(FormSubmission.status == status)
        if form_id:
            q = q.where(FormSubmission.form_id == form_id)
        if since:
            q = q.where(FormSubmission.submitted_at >= since)
        q = q.order_by(FormSubmission.submitted_at.desc()).limit(limit)
        return list(self._s.execute(q).scalars().all())

    def update_status(self, sub_id: int, status: str, *, error_text: str | None = None) -> None:
        row = self._s.get(FormSubmission, sub_id)
        if row is None:
            return
        row.status = status
        if error_text is not None:
            row.error_text = error_text
