from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_api_key
from app.api.deps import readonly_session, readwrite_session
from app.db.models.enums import SiteMode
from app.db.models.page import Page
from app.db.models.site import Site
from app.db.repos.sites import SiteRepository
from app.schemas.site_edit_api import SiteCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sites", tags=["sites"], dependencies=[Depends(require_api_key)])
pages_router = APIRouter(prefix="/pages", tags=["pages"], dependencies=[Depends(require_api_key)])


@router.post("/", status_code=201)
def create_site(
    body: SiteCreate,
    session: Session = Depends(readwrite_session),
) -> dict[str, object]:
    """Создать запись сайта (без контента). После этого:
    - `POST /admin/sites/{slug}/generate` — запустить full pipeline.
    """
    repo = SiteRepository(session)
    if repo.get_by_slug(body.slug) is not None:
        raise HTTPException(status_code=409, detail=f"site slug already exists: {body.slug}")
    site = Site(slug=body.slug, display_name=body.display_name, mode=SiteMode.CUSTOM)
    session.add(site)
    session.commit()
    session.refresh(site)
    logger.info("site_created id=%s slug=%s", site.id, site.slug)
    return {
        "id": site.id,
        "slug": site.slug,
        "display_name": site.display_name,
        "mode": site.mode.value,
    }


@router.get("/")
def list_sites(session: Session = Depends(readonly_session)) -> list[dict[str, object]]:
    rows = list(session.scalars(select(Site).order_by(Site.id)))
    return [
        {
            "id": s.id,
            "slug": s.slug,
            "display_name": s.display_name,
            "mode": s.mode.value if hasattr(s.mode, "value") else str(s.mode),
            "current_version_id": s.current_version_id,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in rows
    ]


@router.get("/{site_slug}")
def get_site(
    site_slug: str,
    session: Session = Depends(readonly_session),
) -> dict[str, object]:
    site = SiteRepository(session).get_by_slug(site_slug)
    if site is None:
        raise HTTPException(status_code=404, detail=f"site not found: {site_slug}")
    return {
        "id": site.id,
        "slug": site.slug,
        "display_name": site.display_name,
        "mode": site.mode.value if hasattr(site.mode, "value") else str(site.mode),
        "current_version_id": site.current_version_id,
    }


@router.get("/{site_slug}/pages")
def list_site_pages(
    site_slug: str,
    session: Session = Depends(readonly_session),
) -> list[dict[str, object]]:
    site = SiteRepository(session).get_by_slug(site_slug)
    if site is None:
        raise HTTPException(status_code=404, detail=f"site not found: {site_slug}")
    rows = list(
        session.scalars(
            select(Page).where(Page.site_id == site.id).order_by(Page.sort_order, Page.id)
        )
    )
    return [
        {
            "id": p.id,
            "slug": p.slug,
            "title": p.title,
            "page_type": p.page_type,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "nav_label": p.nav_label,
            "sort_order": p.sort_order,
        }
        for p in rows
    ]
