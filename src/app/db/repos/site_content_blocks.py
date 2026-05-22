from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.site_content_block import SiteContentBlock


class SiteContentBlockRepository:
    """CRUD для site_content_blocks.

    Главный use-case: `replace_for_page` — bulk-замена набора блоков страницы при
    регенерации контента или дизайн-edit'е (если шаблон поменял порядок секций).
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_page(self, page_id: int) -> list[SiteContentBlock]:
        q = (
            select(SiteContentBlock)
            .where(SiteContentBlock.page_id == page_id)
            .order_by(SiteContentBlock.sort_order.asc(), SiteContentBlock.id.asc())
        )
        return list(self._s.scalars(q).all())

    def replace_for_page(self, page_id: int, blocks: list[dict]) -> list[SiteContentBlock]:
        """Удалить все блоки страницы и записать новые.

        `blocks` — список dict'ов в форме `{"kind": str, "props": dict}` (sort_order
        выставляется автоматически по порядку списка).
        """
        self._s.execute(delete(SiteContentBlock).where(SiteContentBlock.page_id == page_id))
        rows: list[SiteContentBlock] = []
        for i, b in enumerate(blocks):
            row = SiteContentBlock(
                page_id=page_id,
                sort_order=i,
                kind=str(b["kind"]),
                props=dict(b.get("props") or {}),
            )
            self._s.add(row)
            rows.append(row)
        self._s.flush()
        return rows

    def update_props(self, block_id: int, props: dict) -> SiteContentBlock | None:
        row = self._s.get(SiteContentBlock, block_id)
        if row is None:
            return None
        row.props = props
        self._s.flush()
        return row

    def delete(self, block_id: int) -> bool:
        row = self._s.get(SiteContentBlock, block_id)
        if row is None:
            return False
        self._s.delete(row)
        self._s.flush()
        return True
