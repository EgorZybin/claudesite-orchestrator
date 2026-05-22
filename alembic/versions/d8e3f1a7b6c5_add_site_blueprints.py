"""

Revision ID: d8e3f1a7b6c5
Revises: b4c7d9e1a2f3
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d8e3f1a7b6c5"
down_revision = "b4c7d9e1a2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_blueprints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="draft", nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_site_blueprints_site_id"), "site_blueprints", ["site_id"], unique=False)
    op.create_index(op.f("ix_site_blueprints_status"), "site_blueprints", ["status"], unique=False)

    op.create_table(
        "site_blueprint_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("blueprint_id", sa.Integer(), nullable=False),
        sa.Column("target_slug", sa.String(length=512), nullable=False),
        sa.Column("page_type", sa.String(length=64), nullable=True),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("extra_json", sa.JSON(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blueprint_id"], ["site_blueprints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_site_blueprint_items_blueprint_id"), "site_blueprint_items", ["blueprint_id"], unique=False)
    op.create_index(op.f("ix_site_blueprint_items_celery_task_id"), "site_blueprint_items", ["celery_task_id"], unique=False)
    op.create_index(op.f("ix_site_blueprint_items_page_id"), "site_blueprint_items", ["page_id"], unique=False)
    op.create_index(op.f("ix_site_blueprint_items_page_type"), "site_blueprint_items", ["page_type"], unique=False)
    op.create_index(op.f("ix_site_blueprint_items_status"), "site_blueprint_items", ["status"], unique=False)
    op.create_index(op.f("ix_site_blueprint_items_target_slug"), "site_blueprint_items", ["target_slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_site_blueprint_items_target_slug"), table_name="site_blueprint_items")
    op.drop_index(op.f("ix_site_blueprint_items_status"), table_name="site_blueprint_items")
    op.drop_index(op.f("ix_site_blueprint_items_page_type"), table_name="site_blueprint_items")
    op.drop_index(op.f("ix_site_blueprint_items_page_id"), table_name="site_blueprint_items")
    op.drop_index(op.f("ix_site_blueprint_items_celery_task_id"), table_name="site_blueprint_items")
    op.drop_index(op.f("ix_site_blueprint_items_blueprint_id"), table_name="site_blueprint_items")
    op.drop_table("site_blueprint_items")

    op.drop_index(op.f("ix_site_blueprints_status"), table_name="site_blueprints")
    op.drop_index(op.f("ix_site_blueprints_site_id"), table_name="site_blueprints")
    op.drop_table("site_blueprints")
