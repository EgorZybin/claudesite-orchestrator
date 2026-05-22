from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SiteContentBlock(Base):
    """Семантический блок контента страницы.

    `kind` ∈ {heading, paragraph, image, list, quote, table, cta} — описывает
    СМЫСЛ контента (заголовок? абзац? картинка?), а не визуальную композицию.
    Визуальные блоки (hero/features/cta-секции) больше не существуют — их роль
    взяли per-site Jinja2-шаблоны, генерируемые Claude'ом.

    Валидация формы props по `kind` — на pydantic-слое
    (`app.schemas.site_content.ContentBlock` дискриминированный union).
    """

    __tablename__ = "site_content_blocks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"),
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    props: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
    )
