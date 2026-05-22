"""

Revision ID: f8e7d6c5b4a3
Revises: e1a2b3c4d5e6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "f8e7d6c5b4a3"
down_revision = "e1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("job_run_id", sa.Integer(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("task_name", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_events_site_id_created", "job_events", ["site_id", "created_at"])
    op.create_index("ix_job_events_job_run_id", "job_events", ["job_run_id"])

    op.create_table(
        "page_render_cache",
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("nav_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("html", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["page_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("page_id"),
    )


def downgrade() -> None:
    op.drop_table("page_render_cache")
    op.drop_index("ix_job_events_job_run_id", table_name="job_events")
    op.drop_index("ix_job_events_site_id_created", table_name="job_events")
    op.drop_table("job_events")
