from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.page_render_cache import PageRenderCache
from app.db.models.page_revision import PageRevision


class PageRevisionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def next_revision_no(self, page_id: int) -> int:
        q = select(func.max(PageRevision.revision_no)).where(PageRevision.page_id == page_id)
        current = self._s.scalar(q)
        return int(current or 0) + 1

    def create(self, *, page_id: int, revision_no: int, payload: dict) -> PageRevision:
        row = PageRevision(page_id=page_id, revision_no=revision_no, payload=payload)
        self._s.add(row)
        cached = self._s.get(PageRenderCache, page_id)
        if cached is not None:
            self._s.delete(cached)
        self._s.flush()
        return row

    def get_latest(self, page_id: int) -> PageRevision | None:
        q = (
            select(PageRevision)
            .where(PageRevision.page_id == page_id)
            .order_by(PageRevision.revision_no.desc())
            .limit(1)
        )
        return self._s.scalar(q)

    def get_by_page_and_revision_no(self, page_id: int, revision_no: int) -> PageRevision | None:
        q = select(PageRevision).where(
            PageRevision.page_id == page_id,
            PageRevision.revision_no == revision_no,
        )
        return self._s.scalar(q)

    def list_revision_nos_desc(self, page_id: int) -> list[int]:
        q = (
            select(PageRevision.revision_no)
            .where(PageRevision.page_id == page_id)
            .order_by(PageRevision.revision_no.desc())
        )
        return [int(x) for x in self._s.scalars(q).all()]

    def merge_payload(self, revision_id: int, patch: dict) -> None:
        rev = self._s.get(PageRevision, revision_id)
        if rev is None:
            return
        base = dict(rev.payload or {})
        base.update(patch)
        rev.payload = base
        cached = self._s.get(PageRenderCache, rev.page_id)
        if cached is not None:
            self._s.delete(cached)
