from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SiteModule(Base):
    """Site-level shared data — features, stats, testimonials, и т.д.

    `kind` ∈ {features, stats, testimonials, pricing, team, faq, contact_info, footer}.
    Один ряд на пару (site_id, kind). Модуль инжектится в страницы, у которых
    `page.modules_used` содержит его `kind`.

    Шейп `data` валидируется по `kind` на pydantic-слое
    (`app.schemas.site_content.SiteModule` дискриминированный union).
    """

    __tablename__ = "site_modules"
    __table_args__ = (
        UniqueConstraint("site_id", "kind", name="uq_site_modules_site_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
    )
