from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.site_domain import SiteDomain


def normalize_host(raw: str) -> str:
    h = (raw or "").strip().lower()
    if h.startswith("http://"):
        h = h[7:]
    elif h.startswith("https://"):
        h = h[8:]
    h = h.split("/", 1)[0]
    if ":" in h:
        h = h.split(":", 1)[0]
    return h.strip(".")


class SiteDomainRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, domain_id: int) -> SiteDomain | None:
        return self._s.get(SiteDomain, domain_id)

    def get_by_host(self, host: str) -> SiteDomain | None:
        norm = normalize_host(host)
        if not norm:
            return None
        q = select(SiteDomain).where(SiteDomain.host == norm, SiteDomain.is_active.is_(True))
        return self._s.scalar(q)

    def list_for_site(self, site_id: int) -> list[SiteDomain]:
        q = (
            select(SiteDomain)
            .where(SiteDomain.site_id == site_id)
            .order_by(SiteDomain.is_primary.desc(), SiteDomain.host.asc())
        )
        return list(self._s.scalars(q).all())

    def get_primary_for_site(self, site_id: int) -> SiteDomain | None:
        q = select(SiteDomain).where(
            SiteDomain.site_id == site_id,
            SiteDomain.is_primary.is_(True),
            SiteDomain.is_active.is_(True),
        )
        row = self._s.scalar(q)
        if row is not None:
            return row
        q2 = (
            select(SiteDomain)
            .where(SiteDomain.site_id == site_id, SiteDomain.is_active.is_(True))
            .order_by(SiteDomain.host.asc())
            .limit(1)
        )
        return self._s.scalar(q2)

    def create(
        self,
        *,
        site_id: int,
        host: str,
        is_primary: bool = False,
        is_active: bool = True,
    ) -> SiteDomain:
        norm = normalize_host(host)
        row = SiteDomain(
            site_id=site_id,
            host=norm,
            is_primary=is_primary,
            is_active=is_active,
        )
        self._s.add(row)
        self._s.flush()
        if is_primary:
            self._ensure_single_primary(site_id=site_id, keep_id=row.id)
        return row

    def update(
        self,
        row: SiteDomain,
        *,
        host: str | None = None,
        is_primary: bool | None = None,
        is_active: bool | None = None,
    ) -> SiteDomain:
        if host is not None:
            row.host = normalize_host(host)
        if is_primary is not None:
            row.is_primary = is_primary
        if is_active is not None:
            row.is_active = is_active
        self._s.flush()
        if row.is_primary:
            self._ensure_single_primary(site_id=row.site_id, keep_id=row.id)
        return row

    def delete(self, row: SiteDomain) -> None:
        self._s.delete(row)
        self._s.flush()

    def _ensure_single_primary(self, *, site_id: int, keep_id: int) -> None:
        q = select(SiteDomain).where(
            SiteDomain.site_id == site_id,
            SiteDomain.id != keep_id,
            SiteDomain.is_primary.is_(True),
        )
        rows = list(self._s.scalars(q).all())
        for other in rows:
            other.is_primary = False
        self._s.flush()
