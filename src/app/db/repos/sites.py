from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.enums import SiteMode
from app.db.models.site import Site


class SiteRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_slug(self, slug: str) -> Site | None:
        return self._s.scalar(select(Site).where(Site.slug == slug))

    def get_by_id(self, site_id: int) -> Site | None:
        return self._s.get(Site, site_id)

    def create(
        self,
        *,
        slug: str,
        display_name: str | None = None,
        mode: SiteMode = SiteMode.WORDPRESS,
    ) -> Site:
        row = Site(slug=slug, display_name=display_name, mode=mode)
        self._s.add(row)
        self._s.flush()
        return row
