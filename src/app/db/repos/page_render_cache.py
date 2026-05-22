from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models.page_render_cache import PageRenderCache


class PageRenderCacheRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, page_id: int) -> PageRenderCache | None:
        return self._s.get(PageRenderCache, page_id)

    def upsert(
        self,
        *,
        page_id: int,
        revision_id: int,
        nav_fingerprint: str,
        content_hash: str,
        html: str,
    ) -> PageRenderCache:
        row = self._s.get(PageRenderCache, page_id)
        if row is None:
            row = PageRenderCache(page_id=page_id)
            self._s.add(row)
        row.revision_id = revision_id
        row.nav_fingerprint = nav_fingerprint
        row.content_hash = content_hash
        row.html = html
        self._s.flush()
        return row

    def delete_for_page(self, page_id: int) -> None:
        row = self._s.get(PageRenderCache, page_id)
        if row is not None:
            self._s.delete(row)
            self._s.flush()
