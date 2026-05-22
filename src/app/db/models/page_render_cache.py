from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PageRenderCache(Base):
    """Кеш готового HTML публичной страницы (инвалидируется сменой revision или меню)."""

    __tablename__ = "page_render_cache"

    page_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("page_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    nav_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    html: Mapped[str] = mapped_column(Text(), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), server_default=func.now())
