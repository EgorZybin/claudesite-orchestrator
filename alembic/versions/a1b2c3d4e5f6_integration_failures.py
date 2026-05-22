"""

Revision ID: a1b2c3d4e5f6
Revises: f8e7d6c5b4a3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f8e7d6c5b4a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_failures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("job_run_id", sa.Integer(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("error_class", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_run_id"], ["job_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_integration_failures_site_created", "integration_failures", ["site_id", "created_at"])
    op.create_index("ix_integration_failures_job_run", "integration_failures", ["job_run_id"])


def downgrade() -> None:
    op.drop_index("ix_integration_failures_job_run", table_name="integration_failures")
    op.drop_index("ix_integration_failures_site_created", table_name="integration_failures")
    op.drop_table("integration_failures")
