from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import JobRunStatus, JobTaskType


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    task_type: Mapped[JobTaskType] = mapped_column(
        Enum(JobTaskType, native_enum=False, length=32),
        index=True,
    )
    status: Mapped[JobRunStatus] = mapped_column(
        Enum(JobRunStatus, native_enum=False, length=32),
        default=JobRunStatus.PENDING,
        server_default=JobRunStatus.PENDING.value,
        index=True,
    )
    input_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    page_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    iteration_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    turgenev_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tech_log: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    site = relationship("Site")
