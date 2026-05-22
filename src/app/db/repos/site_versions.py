from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.site import Site
from app.db.models.site_version import SiteVersion


class SiteVersionRepository:
    """CRUD для таблицы site_versions + переключение `sites.current_version_id`."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_id(self, version_id: int) -> SiteVersion | None:
        return self._s.get(SiteVersion, version_id)

    def get_current(self, site_id: int) -> SiteVersion | None:
        """Опубликованная (текущая) версия сайта или None если ещё не публиковали."""
        site = self._s.get(Site, site_id)
        if site is None or site.current_version_id is None:
            return None
        return self._s.get(SiteVersion, site.current_version_id)

    def get_by_version_num(self, site_id: int, version_num: int) -> SiteVersion | None:
        q = (
            select(SiteVersion)
            .where(SiteVersion.site_id == site_id)
            .where(SiteVersion.version_num == version_num)
        )
        return self._s.scalars(q).one_or_none()

    def next_version_num(self, site_id: int) -> int:
        q = (
            select(SiteVersion.version_num)
            .where(SiteVersion.site_id == site_id)
            .order_by(SiteVersion.version_num.desc())
            .limit(1)
        )
        last = self._s.scalars(q).one_or_none()
        return (last or 0) + 1

    def list_for_site(self, site_id: int, *, limit: int | None = None) -> list[SiteVersion]:
        q = (
            select(SiteVersion)
            .where(SiteVersion.site_id == site_id)
            .order_by(SiteVersion.version_num.desc())
        )
        if limit is not None:
            q = q.limit(limit)
        return list(self._s.scalars(q).all())

    def create(
        self,
        *,
        site_id: int,
        version_num: int,
        manifest_json: dict,
        git_commit_sha: str | None = None,
        comment: str | None = None,
        status: str = "draft",
    ) -> SiteVersion:
        row = SiteVersion(
            site_id=site_id,
            version_num=version_num,
            manifest_json=manifest_json,
            git_commit_sha=git_commit_sha,
            comment=comment,
            status=status,
        )
        self._s.add(row)
        self._s.flush()
        return row

    def publish(self, version_id: int) -> SiteVersion:
        """Перевести версию в published + указатель `sites.current_version_id`.

        Старая published-версия для того же site_id переводится в `archived`.
        """
        row = self._s.get(SiteVersion, version_id)
        if row is None:
            raise ValueError(f"site_version id={version_id} not found")

        self._s.execute(
            update(SiteVersion)
            .where(SiteVersion.site_id == row.site_id)
            .where(SiteVersion.status == "published")
            .where(SiteVersion.id != row.id)
            .values(status="archived")
        )

        row.status = "published"
        self._s.execute(
            update(Site)
            .where(Site.id == row.site_id)
            .values(current_version_id=row.id)
        )
        self._s.flush()
        return row
