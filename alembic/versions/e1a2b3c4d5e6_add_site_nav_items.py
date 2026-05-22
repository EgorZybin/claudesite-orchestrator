"""

Revision ID: e1a2b3c4d5e6
Revises: d8e3f1a7b6c5
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e1a2b3c4d5e6"
down_revision = "d8e3f1a7b6c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_nav_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=512), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["site_nav_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_site_nav_items_site_id"), "site_nav_items", ["site_id"], unique=False)
    op.create_index(op.f("ix_site_nav_items_parent_id"), "site_nav_items", ["parent_id"], unique=False)
    op.create_index(op.f("ix_site_nav_items_slug"), "site_nav_items", ["slug"], unique=False)
    op.create_index(op.f("ix_site_nav_items_page_id"), "site_nav_items", ["page_id"], unique=False)
    op.create_index(op.f("ix_site_nav_items_sort_order"), "site_nav_items", ["sort_order"], unique=False)
    op.create_index(op.f("ix_site_nav_items_is_visible"), "site_nav_items", ["is_visible"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_site_nav_items_is_visible"), table_name="site_nav_items")
    op.drop_index(op.f("ix_site_nav_items_sort_order"), table_name="site_nav_items")
    op.drop_index(op.f("ix_site_nav_items_page_id"), table_name="site_nav_items")
    op.drop_index(op.f("ix_site_nav_items_slug"), table_name="site_nav_items")
    op.drop_index(op.f("ix_site_nav_items_parent_id"), table_name="site_nav_items")
    op.drop_index(op.f("ix_site_nav_items_site_id"), table_name="site_nav_items")
    op.drop_table("site_nav_items")
