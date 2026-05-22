from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.api.deps import readwrite_session
from app.db.models.enums import JobRunStatus, JobTaskType
from app.db.models.page import Page
from app.db.models.site import Site
from app.db.repos.jobs import JobRunRepository
from app.db.repos.page_render_cache import PageRenderCacheRepository
from app.db.repos.site_content_blocks import SiteContentBlockRepository
from app.db.repos.site_modules import SiteModuleRepository
from app.schemas.site_content import SiteModule
from app.schemas.site_edit_api import (
    BlockRewrite,
    BlocksReplace,
    DesignEdit,
    DomainAdd,
    ModuleUpsert,
    PageAdd,
    PageMetadataPatch,
    PageTypeExtend,
    SiteGenerate,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/admin/sites",
    tags=["admin-site-edit"],
    dependencies=[Depends(require_api_key)],
)


_SITE_MODULE_ADAPTER = TypeAdapter(SiteModule)


def _resolve_site_or_404(session: Session, site_slug: str) -> Site:
    site = session.scalar(select(Site).where(Site.slug == site_slug))
    if site is None:
        raise HTTPException(status_code=404, detail=f"site not found: {site_slug}")
    return site


def _resolve_page_or_404(session: Session, site_id: int, page_slug: str) -> Page:
    page = session.scalar(
        select(Page).where(Page.site_id == site_id, Page.slug == page_slug),
    )
    if page is None:
        raise HTTPException(status_code=404, detail=f"page not found: /{page_slug}")
    return page


def _invalidate_cache(session: Session, *, site_id: int, page_id: int | None = None) -> None:
    """Снести page_render_cache по site_id (+ опц. page_id)."""
    try:
        cache_repo = PageRenderCacheRepository(session)
    except Exception:
        return
    try:
        if page_id is not None:
            cache_repo.delete_for_page(page_id)
        else:
            if hasattr(cache_repo, "delete_for_site"):
                cache_repo.delete_for_site(site_id)
    except Exception as e:
        logger.warning("cache_invalidate_failed site_id=%s page_id=%s err=%s", site_id, page_id, e)


@router.put("/{site_slug}/pages/{page_slug}/blocks")
def replace_page_blocks(
    site_slug: str,
    page_slug: str,
    body: BlocksReplace,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Полная замена `site_content_blocks` страницы (по списку из body)."""
    site = _resolve_site_or_404(session, site_slug)
    page = _resolve_page_or_404(session, site.id, page_slug)

    cb_repo = SiteContentBlockRepository(session)
    blocks_data = [
        {"kind": b.kind, "props": b.props}
        for b in body.blocks
    ]
    rows = cb_repo.replace_for_page(page.id, blocks_data)
    _invalidate_cache(session, site_id=site.id, page_id=page.id)
    session.commit()
    logger.info(
        "edit_blocks_replace site=%s page=%s new_count=%d",
        site_slug, page_slug, len(rows),
    )
    return {"ok": True, "page_id": page.id, "blocks_written": len(rows)}


@router.put("/{site_slug}/modules/{kind}")
def upsert_module(
    site_slug: str,
    kind: str,
    body: ModuleUpsert,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Upsert site-level module по паре (site_id, kind).

    Валидируем `{kind, data}` через `SiteModule` discriminated union — это
    проверит data shape для конкретного kind (features.items, pricing.plans, и т.д.).
    """
    site = _resolve_site_or_404(session, site_slug)

    try:
        _SITE_MODULE_ADAPTER.validate_python({"kind": kind, "data": body.data})
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"module schema validation: {e}") from e

    m_repo = SiteModuleRepository(session)
    m_repo.upsert(site_id=site.id, kind=kind, data=body.data)
    _invalidate_cache(session, site_id=site.id)
    session.commit()
    logger.info("edit_module_upsert site=%s kind=%s", site_slug, kind)
    return {"ok": True, "site_id": site.id, "kind": kind}


@router.patch("/{site_slug}/pages/{page_slug}")
def patch_page_metadata(
    site_slug: str,
    page_slug: str,
    body: PageMetadataPatch,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Точечная правка полей страницы (всё что не None в body → UPDATE).

    Не трогает `slug`, `page_type` (структурные). Не трогает content_blocks
    (для них отдельный эндпойнт). seo_description пишется в seo_overrides JSON.
    """
    site = _resolve_site_or_404(session, site_slug)
    page = _resolve_page_or_404(session, site.id, page_slug)

    updated_fields: list[str] = []
    if body.title is not None:
        page.title = body.title
        updated_fields.append("title")
    if body.seo_description is not None:
        overrides = dict(page.seo_overrides or {})
        overrides["description"] = body.seo_description
        page.seo_overrides = overrides
        updated_fields.append("seo_description")
    if body.hero_title is not None:
        page.hero_title = body.hero_title
        updated_fields.append("hero_title")
    if body.hero_subtitle is not None:
        page.hero_subtitle = body.hero_subtitle
        updated_fields.append("hero_subtitle")
    if body.hero_image is not None:
        page.hero_image = body.hero_image
        updated_fields.append("hero_image")
    if body.nav_label is not None:
        page.nav_label = body.nav_label or None
        updated_fields.append("nav_label")
    if body.nav_order is not None:
        page.nav_order = body.nav_order
        updated_fields.append("nav_order")
    if body.sort_order is not None:
        page.sort_order = body.sort_order
        updated_fields.append("sort_order")
    if body.modules_used is not None:
        page.modules_used = list(body.modules_used)
        updated_fields.append("modules_used")

    if not updated_fields:
        raise HTTPException(status_code=400, detail="no fields to update (body is empty)")

    _invalidate_cache(session, site_id=site.id, page_id=page.id)
    session.commit()
    logger.info(
        "edit_page_patch site=%s page=%s fields=%s",
        site_slug, page_slug, updated_fields,
    )
    return {"ok": True, "page_id": page.id, "updated_fields": updated_fields}


@router.post("/{site_slug}/pages/{page_slug}/blocks/{block_id}/rewrite")
def rewrite_block(
    site_slug: str,
    page_slug: str,
    block_id: int,
    body: BlockRewrite,
) -> dict[str, object]:
    """LLM-rewrite текстового поля одного блока через Celery worker.

    API остаётся синхронным (клиент видит блокирующий запрос), но фактически
    LLM-вызов идёт в worker'е через `.delay() + .get(timeout=60)`. API не имеет
    прямого доступа к gateway — это работа worker'а.
    """
    from celery.exceptions import TimeoutError as CeleryTimeoutError

    from app.workers.tasks import rewrite_block_task

    async_result = rewrite_block_task.delay(
        site_slug, page_slug, block_id, body.instruction,
    )
    try:
        result = async_result.get(timeout=60, disable_sync_subtasks=False)
    except CeleryTimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"rewrite timed out (task_id={async_result.id}); check task status",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"rewrite failed: {e}") from e

    return result


@router.post("/{site_slug}/generate")
def generate_site(
    site_slug: str,
    body: SiteGenerate,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Полная генерация сайта end-to-end: content_plan → expand_prose → persist →
    Claude CLI build → publish. Async (~3-20 мин). Возвращает `job_id`.
    """
    from app.workers.tasks import generate_site_task

    site = _resolve_site_or_404(session, site_slug)
    jobs_repo = JobRunRepository(session)
    job = jobs_repo.create(
        site_id=site.id,
        task_type=JobTaskType.GENERATE_SITE,
        status=JobRunStatus.PENDING,
        input_params={
            "user_prompt": body.user_prompt[:500],
            "target_pages": body.target_pages,
        },
    )
    session.commit()

    async_result = generate_site_task.delay(
        site_slug, body.user_prompt, body.target_pages, job.id,
    )
    job.celery_task_id = async_result.id
    session.commit()

    return {
        "job_id": job.id,
        "status": JobRunStatus.PENDING.value,
        "poll_url": f"/jobs/{job.id}",
    }


@router.post("/{site_slug}/design-edit")
def design_edit(
    site_slug: str,
    body: DesignEdit,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Запустить Claude CLI design-edit. Возвращает job_id; клиент опрашивает `/admin/jobs/{id}`.

    Долгая операция (~10-30 сек минимум, до 15 мин для сложных правок) — async,
    статус трекается в JobRun таблице.
    """
    from app.workers.tasks import design_edit_task

    site = _resolve_site_or_404(session, site_slug)
    jobs_repo = JobRunRepository(session)
    job = jobs_repo.create(
        site_id=site.id,
        task_type=JobTaskType.DESIGN_EDIT,
        status=JobRunStatus.PENDING,
        input_params={"instruction": body.instruction, "scope": body.scope},
    )
    session.commit()

    async_result = design_edit_task.delay(
        job.id,
        site_slug,
        body.instruction,
        body.scope,
        body.timeout_seconds or 900,
    )

    job.celery_task_id = async_result.id
    session.commit()

    return {
        "job_id": job.id,
        "status": JobRunStatus.PENDING.value,
        "poll_url": f"/jobs/{job.id}",
    }


@router.post("/{site_slug}/pages")
def add_page(
    site_slug: str,
    body: PageAdd,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Добавить одну страницу к существующему сайту. Async — возвращает job_id.

    page_type должен быть в manifest.page_types (template уже есть). Если нужен
    новый page_type — сначала `/admin/sites/{slug}/page-types` (Phase 14).
    """
    from app.workers.tasks import add_page_task

    site = _resolve_site_or_404(session, site_slug)
    jobs_repo = JobRunRepository(session)
    job = jobs_repo.create(
        site_id=site.id,
        task_type=JobTaskType.ADD_PAGE,
        status=JobRunStatus.PENDING,
        input_params={
            "slug": body.slug,
            "page_type": body.page_type,
            "keyword": body.keyword,
            "title_hint": body.title_hint,
            "industry": body.industry,
        },
    )
    session.commit()

    async_result = add_page_task.delay(
        job.id,
        site_slug,
        body.slug,
        body.page_type,
        body.keyword,
        body.title_hint,
        body.industry,
        body.skip_expand_prose,
    )

    job.celery_task_id = async_result.id
    session.commit()

    return {
        "job_id": job.id,
        "status": JobRunStatus.PENDING.value,
        "poll_url": f"/jobs/{job.id}",
    }


@router.post("/{site_slug}/page-types")
def add_page_type(
    site_slug: str,
    body: PageTypeExtend,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Добавить новый page_type — Claude генерит template + дописывает manifest.

    Async (Claude CLI ~15-30 сек). Возвращает job_id; клиент опрашивает
    `/admin/jobs/{id}`. После SUCCESS можно сразу добавлять страницы этого
    page_type'а через `/admin/sites/{slug}/pages`.
    """
    from app.workers.tasks import add_page_type_task

    site = _resolve_site_or_404(session, site_slug)
    jobs_repo = JobRunRepository(session)
    job = jobs_repo.create(
        site_id=site.id,
        task_type=JobTaskType.ADD_PAGE_TYPE,
        status=JobRunStatus.PENDING,
        input_params={
            "name": body.name,
            "description": body.description,
            "slots_needed": body.slots_needed,
        },
    )
    session.commit()

    async_result = add_page_type_task.delay(
        job.id,
        site_slug,
        body.name,
        body.description,
        body.slots_needed,
        body.timeout_seconds or 900,
    )

    job.celery_task_id = async_result.id
    session.commit()

    return {
        "job_id": job.id,
        "status": JobRunStatus.PENDING.value,
        "poll_url": f"/jobs/{job.id}",
    }
