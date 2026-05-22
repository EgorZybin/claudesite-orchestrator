from __future__ import annotations

import logging

from app.workers.celery_app import celery_app
from app.workers.tasks import _with_job_run

logger = logging.getLogger(__name__)


def _publish_action_impl(*, site_slug: str, action) -> dict:
    from app.core.site_runtime import SiteRuntimeResolver
    from app.db.session import get_session_factory
    from app.services.wp_publish import publish_action

    factory = get_session_factory()
    with factory() as session:
        rt = SiteRuntimeResolver().resolve(session, site_slug)
        result = publish_action(session=session, rt=rt, action=action)
    return _summarize(result)


def _summarize(result) -> dict:
    return {
        "page_id": result.page_id,
        "slug": result.slug,
        "wp_post_id": result.wp_post_id,
        "title": result.title,
        "post_type": result.post_type,
        "post_status": result.post_status,
        "chars_body_md": result.chars_body_md,
        "humanizer_chain": list(result.humanizer_chain),
        "taxonomy": result.taxonomy,
        "term_slug": result.term_slug,
        "template": result.template,
    }


@celery_app.task(bind=True, name="app.wp.do")
def wp_do_task(self, site_slug: str, instruction: str, job_id: int | None = None) -> dict:
    """Natural-language: router → publish."""

    def _impl():
        from app.core.site_runtime import SiteRuntimeResolver
        from app.db.session import get_session_factory
        from app.services.wp_publish import publish_from_instruction

        factory = get_session_factory()
        with factory() as session:
            rt = SiteRuntimeResolver().resolve(session, site_slug)
            result = publish_from_instruction(session=session, rt=rt, instruction=instruction)
        return _summarize(result)

    if job_id is not None:
        return _with_job_run(job_id, "wp_do")(_impl)()
    return _impl()


@celery_app.task(bind=True, name="app.wp.publish_explicit")
def wp_publish_explicit_task(
    self,
    site_slug: str,
    topic: str,
    post_type: str,
    post_status: str,
    taxonomy: str | None,
    term_slug: str | None,
    template: str | None,
    extra_postmeta: dict | None,
    job_id: int | None = None,
) -> dict:
    """Explicit: action собран извне (без router'а)."""
    from app.services.wp_router import WpAction

    action = WpAction(
        post_type=post_type,
        post_status=post_status,
        topic=topic,
        taxonomy=taxonomy,
        term_slug=term_slug,
        template=template,
        extra_postmeta=extra_postmeta or {},
        rationale="explicit-mode (router skipped)",
    )

    def _impl():
        return _publish_action_impl(site_slug=site_slug, action=action)

    if job_id is not None:
        return _with_job_run(job_id, "wp_publish_explicit")(_impl)()
    return _impl()
