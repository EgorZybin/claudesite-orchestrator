from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.api.deps import readonly_session, readwrite_session
from app.db.repos.form_submissions import FormSubmissionRepository
from app.db.repos.pages import PageRepository
from app.db.repos.sites import SiteRepository

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/sites", tags=["form-submissions"])
admin_router = APIRouter(
    prefix="/sites", tags=["form-submissions"], dependencies=[Depends(require_api_key)]
)


_RESERVED_KEYS = {"__form_id", "__page_slug", "__hp"}


def _site_or_404(session: Session, site_slug: str):
    site = SiteRepository(session).get_by_slug(site_slug)
    if site is None:
        raise HTTPException(status_code=404, detail="site not found")
    return site


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


@public_router.post("/{site_slug}/submit")
async def submit_form(
    request: Request,
    site_slug: str,
    session: Session = Depends(readwrite_session),
) -> Response:
    site = _site_or_404(session, site_slug)

    try:
        form = await request.form()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid form body: {e}")

    raw: dict[str, Any] = {}
    for key in form.keys():
        values = form.getlist(key)
        raw[key] = values[0] if len(values) == 1 else values

    form_id = (raw.get("__form_id") or "unknown").strip().lower()
    page_slug = (raw.get("__page_slug") or "").strip().lower() or None
    honeypot = (raw.get("__hp") or "").strip()
    user_agent = request.headers.get("user-agent", "")[:1024]
    ip = _client_ip(request)

    payload = {k: v for k, v in raw.items() if k not in _RESERVED_KEYS}

    page_id: int | None = None
    if page_slug:
        page = PageRepository(session).get_by_site_and_slug(site.id, page_slug)
        if page is not None:
            page_id = page.id

    initial_status = "spam_honeypot" if honeypot else "pending"

    repo = FormSubmissionRepository(session)
    row = repo.create(
        site_id=site.id,
        page_id=page_id,
        page_slug=page_slug,
        form_id=form_id[:128],
        payload=payload,
        status=initial_status,
        ip=ip,
        user_agent=user_agent,
    )
    sub_id = row.id

    if honeypot:
        logger.info("form_submit_honeypot site=%s form=%s ip=%s", site_slug, form_id, ip)
    else:
        logger.info(
            "form_submit site=%s form=%s page=%s payload_keys=%s",
            site_slug, form_id, page_slug, list(payload.keys()),
        )
        try:
            from app.workers.tasks import notify_form_submission_task

            notify_form_submission_task.delay(sub_id)
        except Exception as e:
            logger.warning("form_submit_dispatch_failed sub_id=%s err=%s", sub_id, e)

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"ok": True, "id": sub_id, "status": initial_status})

    target_path = f"/{page_slug}" if page_slug else "/"
    location = f"{target_path}?submitted=1&form={form_id}"
    return Response(status_code=303, headers={"Location": location})


@admin_router.get("/{site_slug}/submissions")
def list_submissions(
    site_slug: str,
    status: str | None = Query(default=None),
    form_id: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    session: Session = Depends(readonly_session),
) -> list[dict[str, Any]]:
    site = _site_or_404(session, site_slug)
    rows = FormSubmissionRepository(session).list_for_site(
        site_id=site.id, status=status, form_id=form_id, since=since, limit=limit
    )
    return [
        {
            "id": r.id,
            "site_id": r.site_id,
            "page_id": r.page_id,
            "page_slug": r.page_slug,
            "form_id": r.form_id,
            "payload": r.payload,
            "status": r.status,
            "ip": r.ip,
            "user_agent": r.user_agent,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        }
        for r in rows
    ]


@admin_router.patch("/{site_slug}/submissions/{submission_id}")
def update_submission(
    site_slug: str,
    submission_id: int,
    body: dict[str, Any],
    session: Session = Depends(readwrite_session),
) -> dict[str, Any]:
    site = _site_or_404(session, site_slug)
    repo = FormSubmissionRepository(session)
    row = repo.get_by_id(submission_id)
    if row is None or row.site_id != site.id:
        raise HTTPException(status_code=404, detail="submission not found")
    new_status = (body.get("status") or "").strip().lower()
    if new_status not in {"read", "archived", "pending"}:
        raise HTTPException(status_code=400, detail="status must be read|archived|pending")
    repo.update_status(submission_id, new_status)
    return {"ok": True, "id": submission_id, "status": new_status}
