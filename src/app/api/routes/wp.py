from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.api.deps import readwrite_session
from app.core.site_runtime import SiteRuntimeResolver
from app.db.models.enums import JobRunStatus, JobTaskType, SiteMode
from app.db.repos.jobs import JobRunRepository
from app.db.repos.sites import SiteRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sites", tags=["wp"], dependencies=[Depends(require_api_key)])


class WpDoRequest(BaseModel):
    instruction: str = Field(min_length=3, max_length=1000)


class WpPublishExplicitRequest(BaseModel):
    """Explicit-mode: routed action собран на стороне клиента, без LLM-router'а."""
    topic: str = Field(min_length=3, max_length=500)
    post_type: str = Field(default="post", pattern=r"^[a-z0-9_-]+$", max_length=32)
    post_status: str = Field(default="publish", pattern=r"^(publish|draft|pending|private)$")
    taxonomy: str | None = Field(default=None, max_length=64)
    term_slug: str | None = Field(default=None, max_length=200)
    template: str | None = Field(default=None, max_length=128)
    extra_postmeta: dict[str, str] = Field(default_factory=dict)


def _resolve_wp_site_or_404(session: Session, site_slug: str):
    site = SiteRepository(session).get_by_slug(site_slug)
    if site is None:
        raise HTTPException(status_code=404, detail=f"site not found: {site_slug}")
    rt = SiteRuntimeResolver().resolve(session, site_slug)
    if rt.effective_mode != SiteMode.WORDPRESS:
        raise HTTPException(
            status_code=400,
            detail=f"site {site_slug!r} mode is {rt.effective_mode.value!r}, expected 'wordpress'",
        )
    return site


@router.post("/{site_slug}/wp-do")
def wp_do(
    site_slug: str,
    body: WpDoRequest,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Natural-language pipeline: LLM-router → publish."""
    from app.workers.tasks_wp import wp_do_task

    site = _resolve_wp_site_or_404(session, site_slug)
    job = JobRunRepository(session).create(
        site_id=site.id,
        task_type=JobTaskType.WP_DO,
        status=JobRunStatus.PENDING,
        input_params={"instruction": body.instruction[:500]},
    )
    session.commit()

    async_result = wp_do_task.delay(site_slug, body.instruction, job.id)
    job.celery_task_id = async_result.id
    session.commit()
    return {
        "job_id": job.id,
        "status": JobRunStatus.PENDING.value,
        "poll_url": f"/jobs/{job.id}",
    }


@router.post("/{site_slug}/wp-publish-article")
def wp_publish_explicit(
    site_slug: str,
    body: WpPublishExplicitRequest,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Explicit-mode: action собран на стороне клиента."""
    from app.workers.tasks_wp import wp_publish_explicit_task

    site = _resolve_wp_site_or_404(session, site_slug)
    job = JobRunRepository(session).create(
        site_id=site.id,
        task_type=JobTaskType.WP_PUBLISH_ARTICLE,
        status=JobRunStatus.PENDING,
        input_params={
            "topic": body.topic[:500],
            "post_type": body.post_type,
            "post_status": body.post_status,
            "taxonomy": body.taxonomy,
            "term_slug": body.term_slug,
            "template": body.template,
            "extra_postmeta": body.extra_postmeta,
        },
    )
    session.commit()

    async_result = wp_publish_explicit_task.delay(
        site_slug, body.topic, body.post_type, body.post_status,
        body.taxonomy, body.term_slug, body.template, body.extra_postmeta, job.id,
    )
    job.celery_task_id = async_result.id
    session.commit()
    return {
        "job_id": job.id,
        "status": JobRunStatus.PENDING.value,
        "poll_url": f"/jobs/{job.id}",
    }
