from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import PageStatus


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("site_id", "slug", name="uq_pages_site_slug"),
        UniqueConstraint("site_id", "keyword_hash", name="uq_pages_site_keyword_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PageStatus] = mapped_column(
        Enum(PageStatus, native_enum=False, length=32),
        default=PageStatus.DRAFT,
        server_default=PageStatus.DRAFT.value,
        index=True,
    )
    page_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    keyword_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyword_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wp_post_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    template_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    render_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    source_job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    seo_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nav_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    modules_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    hero_image: Mapped[str | None] = mapped_column(String(512), nullable=True)
    hero_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    hero_subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
    )

    site = relationship("Site", back_populates="pages")
    revisions = relationship(
        "PageRevision",
        back_populates="page",
        passive_deletes=True,
    )
