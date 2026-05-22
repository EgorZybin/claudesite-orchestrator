from __future__ import annotations

import hashlib
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.enums import PageStatus
from app.db.models.page import Page
from app.db.models.site_content_block import SiteContentBlock
from app.db.models.site_module import SiteModule
from app.db.repos.site_content_blocks import SiteContentBlockRepository
from app.db.repos.site_modules import SiteModuleRepository
from app.schemas.site_content import SiteContent

logger = logging.getLogger(__name__)


def _keyword_hash(slug: str, keyword: str) -> str:
    return hashlib.sha256(f"{slug}|{keyword}".encode("utf-8")).hexdigest()


def persist_site_content(session: Session, *, site_id: int, content: SiteContent) -> dict[str, int]:
    """Записать pages + content_blocks + modules в MySQL.

    Возвращает {pages: N, content_blocks: M, modules: K} с количеством записей.
    Перед записью удаляет существующие pages этого сайта (CASCADE сметёт
    content_blocks автоматически) и site_modules — это full-replace
    (для initial build). Edit-flow в Phase 10-11 будет делать точечные UPDATE
    через свои API без вызова этой функции.
    """
    from app.db.models.site import Site as _SiteModel
    site_row = session.get(_SiteModel, site_id)
    if site_row is not None:
        site_row.display_name = content.site_meta.brand
        if content.site_meta.industry:
            site_row.industry = content.site_meta.industry
        if content.site_meta.language:
            site_row.language = content.site_meta.language

    session.execute(delete(Page).where(Page.site_id == site_id))
    session.execute(delete(SiteModule).where(SiteModule.site_id == site_id))
    session.flush()

    cb_repo = SiteContentBlockRepository(session)
    m_repo = SiteModuleRepository(session)

    pages_inserted = 0
    blocks_inserted = 0
    for idx, p in enumerate(content.pages):
        page_row = Page(
            site_id=site_id,
            slug=p.slug,
            title=p.title,
            status=PageStatus.PUBLISHED,
            page_type=p.page_type,
            keyword_raw=p.title,
            keyword_hash=_keyword_hash(p.slug, p.title),
            content_hash=None,
            seo_overrides={"description": p.seo_description},
            nav_label=p.nav_label,
            sort_order=p.nav_order if p.nav_order is not None else idx,
            modules_used=list(p.modules_used or []),
            hero_image=p.hero_image,
            hero_title=p.hero_title,
            hero_subtitle=p.hero_subtitle,
        )
        session.add(page_row)
        session.flush()

        blocks_data = [
            {"kind": b.kind, "props": b.props}
            for b in p.content_blocks
        ]
        if blocks_data:
            cb_repo.replace_for_page(page_row.id, blocks_data)
            blocks_inserted += len(blocks_data)

        pages_inserted += 1

    modules_inserted = 0
    for mod in content.modules:
        m_repo.upsert(site_id=site_id, kind=mod.kind, data=mod.data)
        modules_inserted += 1

    logger.info(
        "persist_site_content site_id=%s pages=%d content_blocks=%d modules=%d",
        site_id,
        pages_inserted,
        blocks_inserted,
        modules_inserted,
    )
    return {
        "pages": pages_inserted,
        "content_blocks": blocks_inserted,
        "modules": modules_inserted,
    }
