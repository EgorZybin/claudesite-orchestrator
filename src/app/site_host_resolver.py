from __future__ import annotations

import logging

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.db.models.site import Site
from app.db.models.site_domain import SiteDomain
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)

_BYPASS_PREFIXES = (
    "/health",
    "/healthz",
    "/metrics",
    "/openapi",
    "/docs",
    "/redoc",
    "/static",
    "/uploads",
    "/assets",
    "/jobs",
    "/admin",
    "/sites",
    "/public",
)


def _normalize_host(raw: str) -> str:
    """Strip port + lowercase host. `lawy.example.com:443` → `lawy.example.com`."""
    if not raw:
        return ""
    h = raw.lower().split(":", 1)[0].strip(".")
    return h


class SiteHostResolverMiddleware(BaseHTTPMiddleware):
    """Resolves Host header to a site, rewrites request path to `/public/{slug}/...`.

    Не активна на bypass-путях (см. `_BYPASS_PREFIXES`). Не активна, если Host
    не находится ни в одном `site_domains.host`.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _BYPASS_PREFIXES):
            return await call_next(request)

        host = _normalize_host(request.headers.get("host", ""))
        if not host:
            return await call_next(request)

        site_slug = self._lookup_site_slug(host)
        if site_slug is None:
            return await call_next(request)

        rewritten = f"/public/{site_slug}"
        if path and path != "/":
            rewritten = f"/public/{site_slug}{path}"
        request.scope["path"] = rewritten
        request.scope["raw_path"] = rewritten.encode("utf-8")

        request.state.via_host_dispatch = True
        request.state.via_host_host = host
        request.state.via_host_original_path = path
        request.state.via_host_site_slug = site_slug

        logger.debug("site_host_rewrite host=%s path=%s → %s", host, path, rewritten)
        return await call_next(request)

    @staticmethod
    def _lookup_site_slug(host: str) -> str | None:
        """Один SQL-join: site_domains.host → sites.slug. Возвращает None если нет."""
        factory = get_session_factory()
        with factory() as s:
            q = (
                select(Site.slug)
                .join(SiteDomain, SiteDomain.site_id == Site.id)
                .where(SiteDomain.host == host)
                .where(SiteDomain.is_active.is_(True))
                .limit(1)
            )
            return s.scalar(q)
