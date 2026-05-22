from __future__ import annotations

import logging
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import readonly_session
from app.db.models.page import Page
from app.db.models.site import Site
from app.db.repos.site_content_blocks import SiteContentBlockRepository
from app.db.repos.site_modules import SiteModuleRepository
from app.db.repos.site_versions import SiteVersionRepository
from app.services.site_build.render import RenderError, SiteRenderer
from app.services.site_build.storage import FilesystemSiteStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public"])


def _resolve_and_render(
    site_slug: str,
    page_slug: str | None,
    request: Request,
    session: Session,
) -> HTMLResponse:
    """Общая логика: site → version → page → blocks → modules → render."""
    site = session.scalar(select(Site).where(Site.slug == site_slug))
    if site is None:
        raise HTTPException(status_code=404, detail=f"site not found: {site_slug}")

    versions_repo = SiteVersionRepository(session)
    current_version = versions_repo.get_current(site.id)
    if current_version is None:
        raise HTTPException(
            status_code=404,
            detail=f"site {site_slug} has no published version yet",
        )

    pages = list(
        session.scalars(
            select(Page).where(Page.site_id == site.id).order_by(Page.sort_order)
        )
    )
    if not pages:
        raise HTTPException(status_code=404, detail=f"site {site_slug} has no pages")

    if not page_slug:
        page = next((p for p in pages if p.page_type == "home"), pages[0])
    else:
        clean_slug = page_slug.rstrip("/")
        page = next((p for p in pages if p.slug == clean_slug), None)
        if page is None:
            raise HTTPException(status_code=404, detail=f"page not found: /{page_slug}")

    cb_repo = SiteContentBlockRepository(session)
    m_repo = SiteModuleRepository(session)
    blocks = cb_repo.list_for_page(page.id)

    modules_to_fetch = list(page.modules_used or [])
    if "footer" not in modules_to_fetch:
        modules_to_fetch.append("footer")
    modules = m_repo.fetch_many(site.id, modules_to_fetch)

    storage = FilesystemSiteStorage(session)
    site_dir = storage.current_dir(site.id).resolve()
    try:
        renderer = SiteRenderer(
            site_id=site.id,
            site_dir=site_dir,
            assets_prefix=f"/assets/{site.id}/current",
        )
    except RenderError as e:
        logger.exception("public_render_init_failed site=%s page=%s", site.slug, page.slug)
        raise HTTPException(status_code=500, detail=f"renderer init failed: {e}") from e

    page_view = SimpleNamespace(
        page_type=page.page_type,
        title=page.title,
        seo_description=(page.seo_overrides or {}).get("description", ""),
        hero_title=page.hero_title,
        hero_subtitle=page.hero_subtitle,
        modules_used=list(page.modules_used or []),
    )
    site_view = SimpleNamespace(
        brand=site.display_name or site.slug,
        language="ru",                                  # TODO: persist per-site language later
        industry="unknown",
        tagline=None,
    )

    via_host = bool(getattr(request.state, "via_host_dispatch", False))
    if via_host:
        host_url_base = f"https://{request.state.via_host_host}"
        nav_prefix = ""
        canonical_path = request.state.via_host_original_path or "/"
    else:
        host_url_base = str(request.base_url).rstrip("/")
        nav_prefix = f"/public/{site_slug}"
        canonical_path = f"/public/{site_slug}" + ("" if not page_slug else f"/{page_slug.rstrip('/')}")

    nav_items = [
        {
            "label": p.nav_label,
            "href": nav_prefix + ("" if p.page_type == "home" else f"/{p.slug}"),
            "current": p.id == page.id,
        }
        for p in pages
        if p.nav_label
    ]
    canonical_url = host_url_base + canonical_path

    try:
        html = renderer.render_page(
            page=page_view,
            content_blocks=blocks,
            modules=modules,
            site=site_view,
            nav=nav_items,
            current_url=canonical_url,
        )
    except RenderError as e:
        logger.exception("public_render_failed site=%s page=%s", site.slug, page.slug)
        raise HTTPException(status_code=500, detail=f"render failed: {e}") from e

    return HTMLResponse(
        content=html,
        headers={
            "X-Site-Version": str(current_version.version_num),
            "Cache-Control": "public, max-age=60",
        },
    )


@router.get("/{site_slug}", response_class=HTMLResponse)
def public_home(
    site_slug: str,
    request: Request,
    session: Session = Depends(readonly_session),
) -> HTMLResponse:
    return _resolve_and_render(site_slug, page_slug=None, request=request, session=session)


@router.get("/{site_slug}/", response_class=HTMLResponse)
def public_home_slash(
    site_slug: str,
    request: Request,
    session: Session = Depends(readonly_session),
) -> HTMLResponse:
    return _resolve_and_render(site_slug, page_slug=None, request=request, session=session)


@router.get("/{site_slug}/{page_slug:path}", response_class=HTMLResponse)
def public_page(
    site_slug: str,
    page_slug: str,
    request: Request,
    session: Session = Depends(readonly_session),
) -> HTMLResponse:
    return _resolve_and_render(site_slug, page_slug=page_slug, request=request, session=session)
