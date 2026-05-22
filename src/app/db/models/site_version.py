from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SiteVersion(Base):
    """Снимок сборки сайта — результат Claude CLI design generation или дизайн-правки.

    Каждая запись = одна опубликованная или черновая версия templates+CSS+JS для сайта.
    Сами файлы лежат на диске в `/var/claudesite/sites/{site_id}/v{version_num}/`.
    Текущая версия указывается в `sites.current_version_id`.
    """

    __tablename__ = "site_versions"
    __table_args__ = (
        UniqueConstraint("site_id", "version_num", name="uq_site_versions_site_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"),
        index=True,
    )
    version_num: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16),
        default="draft",
        server_default="draft",
        index=True,
    )
    manifest_json: Mapped[dict] = mapped_column(JSON)
    git_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
    )
