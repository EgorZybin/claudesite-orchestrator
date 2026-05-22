from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models.enums import PageStatus
from app.db.models.page import Page


class PageRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get_by_site_and_slug(self, site_id: int, slug: str) -> Page | None:
        q = select(Page).where(Page.site_id == site_id, Page.slug == slug)
        return self._s.scalar(q)

    def get_by_site_and_keyword_hash(self, site_id: int, keyword_hash: str) -> Page | None:
        q = select(Page).where(Page.site_id == site_id, Page.keyword_hash == keyword_hash)
        return self._s.scalar(q)

    def get_by_id(self, page_id: int) -> Page | None:
        return self._s.get(Page, page_id)

    def get_published_by_site_and_slug(self, site_id: int, slug: str) -> Page | None:
        q = select(Page).where(
            Page.site_id == site_id,
            Page.slug == slug,
            Page.status == PageStatus.PUBLISHED,
            Page.deleted_at.is_(None),
        )
        return self._s.scalar(q)

    def list_published_for_site(self, site_id: int) -> list[Page]:
        q = (
            select(Page)
            .where(
                Page.site_id == site_id,
                Page.status == PageStatus.PUBLISHED,
                Page.deleted_at.is_(None),
            )
            .order_by(Page.slug.asc())
        )
        return list(self._s.scalars(q).all())

    def list_published_for_site_by_type(self, site_id: int, page_type: str) -> list[Page]:
        """Опубликованные страницы одного page_type, новые сверху.

        Источник для динамического блока ``page_list`` (списки статей блога,
        обзорные страницы услуг). Сортировка по created_at — стабильна при
        правках контента (в отличие от updated_at)."""
        q = (
            select(Page)
            .where(
                Page.site_id == site_id,
                Page.status == PageStatus.PUBLISHED,
                Page.deleted_at.is_(None),
                Page.page_type == page_type,
            )
            .order_by(Page.created_at.desc(), Page.id.desc())
        )
        return list(self._s.scalars(q).all())

    def list_for_site_cursor(
        self,
        site_id: int,
        *,
        limit: int,
        after_updated_at: datetime | None = None,
        after_id: int | None = None,
        include_deleted: bool = False,
    ) -> list[Page]:
        """Сначала новые по (updated_at desc, id desc). Для следующей страницы передать after_*."""
        q = select(Page).where(Page.site_id == site_id)
        if not include_deleted:
            q = q.where(Page.deleted_at.is_(None))
        if after_updated_at is not None and after_id is not None:
            q = q.where(
                or_(
                    Page.updated_at < after_updated_at,
                    and_(Page.updated_at == after_updated_at, Page.id < after_id),
                )
            )
        q = q.order_by(Page.updated_at.desc(), Page.id.desc()).limit(limit)
        return list(self._s.scalars(q).all())

    def update_page(self, page: Page, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(page, k, v)

    def create(
        self,
        *,
        site_id: int,
        slug: str,
        title: str | None = None,
        status: PageStatus = PageStatus.DRAFT,
        page_type: str | None = None,
        keyword_raw: str | None = None,
        keyword_hash: str | None = None,
        seo_overrides: dict | None = None,
    ) -> Page:
        row = Page(
            site_id=site_id,
            slug=slug,
            title=title,
            status=status,
            page_type=page_type,
            keyword_raw=keyword_raw,
            keyword_hash=keyword_hash,
            seo_overrides=seo_overrides,
        )
        self._s.add(row)
        self._s.flush()
        return row
