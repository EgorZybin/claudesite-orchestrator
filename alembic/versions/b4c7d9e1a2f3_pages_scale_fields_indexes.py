"""

Revision ID: b4c7d9e1a2f3
Revises: 9f1b6d2e4c11
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b4c7d9e1a2f3"
down_revision = "9f1b6d2e4c11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("template_name", sa.String(length=128), nullable=True))
    op.add_column(
        "pages",
        sa.Column("render_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("pages", sa.Column("source_job_run_id", sa.Integer(), nullable=True))
    op.add_column("pages", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("pages", sa.Column("published_at", sa.DateTime(), nullable=True))
    op.add_column("pages", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    op.create_foreign_key(
        "fk_pages_source_job_run_id_job_runs",
        "pages",
        "job_runs",
        ["source_job_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(op.f("ix_pages_source_job_run_id"), "pages", ["source_job_run_id"], unique=False)
    op.create_index(op.f("ix_pages_content_hash"), "pages", ["content_hash"], unique=False)
    op.create_index(op.f("ix_pages_published_at"), "pages", ["published_at"], unique=False)
    op.create_index(op.f("ix_pages_deleted_at"), "pages", ["deleted_at"], unique=False)

    op.create_index("ix_pages_site_status_page_type", "pages", ["site_id", "status", "page_type"], unique=False)
    op.create_index("ix_pages_site_published_at", "pages", ["site_id", "published_at"], unique=False)
    op.create_index("ix_pages_site_updated_at", "pages", ["site_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pages_site_updated_at", table_name="pages")
    op.drop_index("ix_pages_site_published_at", table_name="pages")
    op.drop_index("ix_pages_site_status_page_type", table_name="pages")

    op.drop_index(op.f("ix_pages_deleted_at"), table_name="pages")
    op.drop_index(op.f("ix_pages_published_at"), table_name="pages")
    op.drop_index(op.f("ix_pages_content_hash"), table_name="pages")
    op.drop_index(op.f("ix_pages_source_job_run_id"), table_name="pages")

    op.drop_constraint("fk_pages_source_job_run_id_job_runs", "pages", type_="foreignkey")

    op.drop_column("pages", "deleted_at")
    op.drop_column("pages", "published_at")
    op.drop_column("pages", "content_hash")
    op.drop_column("pages", "source_job_run_id")
    op.drop_column("pages", "render_version")
    op.drop_column("pages", "template_name")
