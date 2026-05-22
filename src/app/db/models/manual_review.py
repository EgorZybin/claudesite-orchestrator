from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import ManualReviewStatus


class ManualReviewQueue(Base):
    __tablename__ = "manual_review_queue"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), index=True)
    job_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ManualReviewStatus] = mapped_column(
        Enum(ManualReviewStatus, native_enum=False, length=16),
        default=ManualReviewStatus.PENDING,
        server_default=ManualReviewStatus.PENDING.value,
        index=True,
    )
    last_turgenev_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    turgenev_remarks: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    last_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("page_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
    )

    page = relationship("Page")
    job_run = relationship("JobRun")
