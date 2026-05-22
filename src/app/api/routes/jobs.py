from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.api.deps import readonly_session
from app.api.serialize import job_run_to_dict
from app.db.repos.jobs import JobRunRepository

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_api_key)])


@router.get("/{job_id}")
def get_job(job_id: int, session: Session = Depends(readonly_session)) -> dict[str, object]:
    row = JobRunRepository(session).get_by_id(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job_run_to_dict(row)


@router.get("/{job_id}/logs")
def get_job_logs(job_id: int, session: Session = Depends(readonly_session)) -> dict[str, object]:
    row = JobRunRepository(session).get_by_id(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"tech_log": row.tech_log}
