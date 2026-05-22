from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.site_module import SiteModule


class SiteModuleRepository:
    """Site-level shared data: features, stats, team, и т.д.

    Уникальный ключ — пара (site_id, kind). Модуль один на сайт по каждому виду,
    инжектится в страницы у которых page.modules_used содержит kind.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, site_id: int, kind: str) -> SiteModule | None:
        q = (
            select(SiteModule)
            .where(SiteModule.site_id == site_id)
            .where(SiteModule.kind == kind)
        )
        return self._s.scalars(q).one_or_none()

    def list_for_site(self, site_id: int) -> list[SiteModule]:
        q = (
            select(SiteModule)
            .where(SiteModule.site_id == site_id)
            .order_by(SiteModule.kind.asc())
        )
        return list(self._s.scalars(q).all())

    def fetch_many(self, site_id: int, kinds: list[str]) -> dict[str, SiteModule]:
        """Вернуть { kind: SiteModule } для запрошенных видов (отсутствующие — нет в dict)."""
        if not kinds:
            return {}
        q = (
            select(SiteModule)
            .where(SiteModule.site_id == site_id)
            .where(SiteModule.kind.in_(kinds))
        )
        return {row.kind: row for row in self._s.scalars(q).all()}

    def upsert(self, *, site_id: int, kind: str, data: dict) -> SiteModule:
        existing = self.get(site_id, kind)
        if existing is None:
            row = SiteModule(site_id=site_id, kind=kind, data=data)
            self._s.add(row)
            self._s.flush()
            return row
        existing.data = data
        self._s.flush()
        return existing

    def delete(self, site_id: int, kind: str) -> bool:
        existing = self.get(site_id, kind)
        if existing is None:
            return False
        self._s.delete(existing)
        self._s.flush()
        return True
