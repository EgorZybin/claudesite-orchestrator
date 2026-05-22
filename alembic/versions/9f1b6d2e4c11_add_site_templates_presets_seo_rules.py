"""

Revision ID: 9f1b6d2e4c11
Revises: c2a8b1d4e5f2
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "9f1b6d2e4c11"
down_revision = "c2a8b1d4e5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_seo_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("title_template", sa.Text(), nullable=True),
        sa.Column("description_template", sa.Text(), nullable=True),
        sa.Column("robots_template", sa.String(length=255), nullable=True),
        sa.Column("canonical_template", sa.Text(), nullable=True),
        sa.Column("default_og_image", sa.String(length=1024), nullable=True),
        sa.Column("schema_type_default", sa.String(length=64), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id"),
    )
    op.create_index(op.f("ix_site_seo_rules_site_id"), "site_seo_rules", ["site_id"], unique=True)

    op.create_table(
        "site_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("theme_name", sa.String(length=128), nullable=True),
        sa.Column("tokens_json", sa.JSON(), nullable=True),
        sa.Column("layout_json", sa.JSON(), nullable=True),
        sa.Column("css_bundle", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id"),
    )
    op.create_index(op.f("ix_site_templates_site_id"), "site_templates", ["site_id"], unique=True)

    op.create_table(
        "page_type_presets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("page_type", sa.String(length=64), nullable=False),
        sa.Column("template_name", sa.String(length=128), nullable=True),
        sa.Column("default_blocks_json", sa.JSON(), nullable=True),
        sa.Column("default_seo_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "page_type", name="uq_page_type_presets_site_page_type"),
    )
    op.create_index(op.f("ix_page_type_presets_page_type"), "page_type_presets", ["page_type"], unique=False)
    op.create_index(op.f("ix_page_type_presets_site_id"), "page_type_presets", ["site_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_page_type_presets_site_id"), table_name="page_type_presets")
    op.drop_index(op.f("ix_page_type_presets_page_type"), table_name="page_type_presets")
    op.drop_table("page_type_presets")

    op.drop_index(op.f("ix_site_templates_site_id"), table_name="site_templates")
    op.drop_table("site_templates")

    op.drop_index(op.f("ix_site_seo_rules_site_id"), table_name="site_seo_rules")
    op.drop_table("site_seo_rules")
