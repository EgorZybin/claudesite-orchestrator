from __future__ import annotations

import logging
from types import SimpleNamespace

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import readonly_session
from app.core.config import get_settings
from app.db.models.page import Page
from app.db.models.site import Site
from app.db.repos.site_content_blocks import SiteContentBlockRepository
from app.db.repos.site_modules import SiteModuleRepository
from app.db.repos.site_versions import SiteVersionRepository
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

    fallback_404 = False
    if not page_slug:
        page = next((p for p in pages if p.page_type == "home"), pages[0])
    else:
        clean_slug = page_slug.rstrip("/")
        page = next((p for p in pages if p.slug == clean_slug), None)
        if page is None:
            storage_check = FilesystemSiteStorage(session)
            site_dir_check = storage_check.current_dir(site.id).resolve()
            if not (site_dir_check / "templates" / "404.html").exists():
                raise HTTPException(status_code=404, detail=f"page not found: /{page_slug}")
            fallback_404 = True
            page = SimpleNamespace(
                id=-1, slug="404", page_type="404",
                title="Страница не найдена",
                seo_overrides={"description": ""},
                hero_title=None, hero_subtitle=None, hero_image=None,
                modules_used=[],
                nav_label=None, sort_order=0,
            )

    cb_repo = SiteContentBlockRepository(session)
    m_repo = SiteModuleRepository(session)
    blocks = cb_repo.list_for_page(page.id)

    modules = {m.kind: m for m in m_repo.list_for_site(site.id)}

    storage = FilesystemSiteStorage(session)
    site_dir = str(storage.current_dir(site.id).resolve())

    page_view = {
        "slug": page.slug,
        "page_type": page.page_type,
        "title": page.title,
        "seo_description": (page.seo_overrides or {}).get("description", ""),
        "hero_title": page.hero_title,
        "hero_subtitle": page.hero_subtitle,
        "hero_image": getattr(page, "hero_image", None),
        "content_blocks": [
            {"kind": b.kind, **(b.props or {})} for b in blocks
        ],
        "modules_used": list(page.modules_used or []),
    }
    site_view = {
        "brand": site.display_name or site.slug,
        "language": site.language or "ru",
        "industry": site.industry or "unknown",
        "tagline": None,
    }

    via_host = bool(getattr(request.state, "via_host_dispatch", False))
    if via_host:
        host_url_base = f"https://{request.state.via_host_host}"
        nav_prefix = ""
        canonical_path = request.state.via_host_original_path or "/"
    else:
        host_url_base = str(request.base_url).rstrip("/")
        nav_prefix = f"/public/{site_slug}"
        canonical_path = f"/public/{site_slug}" + ("" if not page_slug else f"/{page_slug.rstrip('/')}")

    def _page_href(p: Page) -> str:
        """URL до страницы p — учитывает via-host vs orchestrator-prefix."""
        if p.page_type == "home":
            return nav_prefix or "/"
        return nav_prefix + f"/{p.slug}"

    nav_items = [
        {
            "label": p.nav_label,
            "href": _page_href(p),
            "current": p.id == page.id,
        }
        for p in pages
        if p.nav_label
    ]

    pages_in_site = [
        {
            "slug": p.slug,
            "title": p.title,
            "page_type": p.page_type,
            "href": _page_href(p),
            "nav_label": p.nav_label,
            "sort_order": p.sort_order,
            "seo_description": (p.seo_overrides or {}).get("description", ""),
            "hero_title": p.hero_title,
            "hero_subtitle": p.hero_subtitle,
            "hero_image": p.hero_image,
        }
        for p in pages
    ]

    canonical_url = host_url_base + canonical_path

    modules_view = {
        kind: (row.data if row is not None else None)
        for kind, row in modules.items()
    }

    props = {
        "site": site_view,
        "page": page_view,
        "modules": modules_view,
        "nav": nav_items,
        "current_url": canonical_url,
        "pages_in_site": pages_in_site,
    }

    settings = get_settings()
    try:
        with httpx.Client(
            timeout=settings.react_renderer_render_timeout_seconds,
        ) as client:
            resp = client.post(
                f"{settings.react_renderer_url}/render",
                json={"site_dir": site_dir, "props": props},
            )
    except httpx.HTTPError as e:
        logger.exception("public_render_http_failed site=%s page=%s", site.slug, page.slug)
        raise HTTPException(status_code=502, detail=f"renderer unreachable: {e}") from e

    if resp.status_code != 200:
        body_snippet = (resp.text or "")[:500]
        logger.warning(
            "public_render_failed site=%s page=%s status=%s body=%s",
            site.slug, page.slug, resp.status_code, body_snippet,
        )
        raise HTTPException(
            status_code=502 if resp.status_code >= 500 else resp.status_code,
            detail=f"renderer error: HTTP {resp.status_code}: {body_snippet}",
        )

    return HTMLResponse(
        content=resp.text,
        status_code=404 if fallback_404 else 200,
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


@router.get("/{site_slug}/assets/{rel_path:path}")
def public_asset(
    site_slug: str,
    rel_path: str,
    session: Session = Depends(readonly_session),
):
    """Serve per-site Vite-built assets (CSS/JS bundles, fonts, images).

    The browser requests `/assets/<hashed>.{css,js}` against the site's
    own host. The host-dispatch middleware rewrites that to
    `/public/<slug>/assets/...` which lands here. We serve from
    `/var/claudesite/sites/<id>/current/dist/client/assets/<rel>`.

    Hashed filenames → safe to cache `immutable`.
    """
    import mimetypes
    from fastapi.responses import FileResponse

    if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
        raise HTTPException(status_code=400, detail="invalid asset path")

    site = session.scalar(select(Site).where(Site.slug == site_slug))
    if site is None:
        raise HTTPException(status_code=404, detail=f"site not found: {site_slug}")

    storage = FilesystemSiteStorage(session)
    base = storage.current_dir(site.id).resolve() / "dist" / "client" / "assets"
    target = (base / rel_path).resolve()

    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path escapes asset root") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"asset not found: {rel_path}")

    content_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        path=str(target),
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{site_slug}/{page_slug:path}", response_class=HTMLResponse)
def public_page(
    site_slug: str,
    page_slug: str,
    request: Request,
    session: Session = Depends(readonly_session),
) -> HTMLResponse:
    return _resolve_and_render(site_slug, page_slug=page_slug, request=request, session=session)
