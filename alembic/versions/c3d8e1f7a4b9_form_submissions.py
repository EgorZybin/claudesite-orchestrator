"""form_submissions table

Revision ID: c3d8e1f7a4b9
Revises: b7c8d9e0f1a2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d8e1f7a4b9"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_submissions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("page_slug", sa.String(length=512), nullable=True),
        sa.Column("form_id", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_form_submissions_site_id_submitted_at",
        "form_submissions",
        ["site_id", "submitted_at"],
        unique=False,
    )
    op.create_index(
        "ix_form_submissions_form_id",
        "form_submissions",
        ["form_id"],
        unique=False,
    )
    op.create_index(
        "ix_form_submissions_status",
        "form_submissions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_form_submissions_page_id",
        "form_submissions",
        ["page_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_form_submissions_page_id", table_name="form_submissions")
    op.drop_index("ix_form_submissions_status", table_name="form_submissions")
    op.drop_index("ix_form_submissions_form_id", table_name="form_submissions")
    op.drop_index("ix_form_submissions_site_id_submitted_at", table_name="form_submissions")
    op.drop_table("form_submissions")
