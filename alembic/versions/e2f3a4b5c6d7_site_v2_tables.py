"""Add tables for new per-site CSS/JS architecture.

Adds:
- site_versions: per-site build snapshots (templates+CSS+JS), versioned
- site_content_blocks: semantic content blocks per page (heading, paragraph, ...)
- site_modules: site-level shared data (features, stats, team, ...)
- pages.nav_label, pages.sort_order, pages.modules_used,
  pages.hero_image, pages.hero_title, pages.hero_subtitle
- sites.current_version_id (FK to site_versions, SET NULL on delete)

Does NOT drop the old R1 tables (site_blueprints, site_blueprint_items,
site_nav_items) — that happens in the final cleanup migration (Phase 15).

Revision ID: e2f3a4b5c6d7
Revises: c3d8e1f7a4b9
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "c3d8e1f7a4b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- site_versions --------------------------------------------------
    op.create_table(
        "site_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("version_num", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("git_commit_sha", sa.String(length=40), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "version_num", name="uq_site_versions_site_version"),
    )
    op.create_index(op.f("ix_site_versions_site_id"), "site_versions", ["site_id"], unique=False)
    op.create_index(op.f("ix_site_versions_status"), "site_versions", ["status"], unique=False)

    # ---- site_content_blocks --------------------------------------------
    op.create_table(
        "site_content_blocks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("page_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("props", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_site_content_blocks_page_id"), "site_content_blocks", ["page_id"], unique=False,
    )

    # ---- site_modules ---------------------------------------------------
    op.create_table(
        "site_modules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "kind", name="uq_site_modules_site_kind"),
    )
    op.create_index(op.f("ix_site_modules_site_id"), "site_modules", ["site_id"], unique=False)
    op.create_index(op.f("ix_site_modules_kind"), "site_modules", ["kind"], unique=False)

    # ---- sites: current_version_id --------------------------------------
    # FK to site_versions — must be created AFTER site_versions table exists (above).
    op.add_column(
        "sites",
        sa.Column("current_version_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sites_current_version_id",
        source_table="sites",
        referent_table="site_versions",
        local_cols=["current_version_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # ---- pages: nav_label, sort_order, modules_used, hero_* -------------
    op.add_column("pages", sa.Column("nav_label", sa.String(length=120), nullable=True))
    op.add_column("pages", sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False))
    op.add_column("pages", sa.Column("modules_used", sa.JSON(), nullable=True))
    op.add_column("pages", sa.Column("hero_image", sa.String(length=512), nullable=True))
    op.add_column("pages", sa.Column("hero_title", sa.String(length=300), nullable=True))
    op.add_column("pages", sa.Column("hero_subtitle", sa.Text(), nullable=True))
    op.create_index(op.f("ix_pages_sort_order"), "pages", ["sort_order"], unique=False)


def downgrade() -> None:
    # Reverse order: drop FK first, then columns, then tables.
    op.drop_index(op.f("ix_pages_sort_order"), table_name="pages")
    op.drop_column("pages", "hero_subtitle")
    op.drop_column("pages", "hero_title")
    op.drop_column("pages", "hero_image")
    op.drop_column("pages", "modules_used")
    op.drop_column("pages", "sort_order")
    op.drop_column("pages", "nav_label")

    op.drop_constraint("fk_sites_current_version_id", "sites", type_="foreignkey")
    op.drop_column("sites", "current_version_id")

    op.drop_index(op.f("ix_site_modules_kind"), table_name="site_modules")
    op.drop_index(op.f("ix_site_modules_site_id"), table_name="site_modules")
    op.drop_table("site_modules")

    op.drop_index(op.f("ix_site_content_blocks_page_id"), table_name="site_content_blocks")
    op.drop_table("site_content_blocks")

    op.drop_index(op.f("ix_site_versions_status"), table_name="site_versions")
    op.drop_index(op.f("ix_site_versions_site_id"), table_name="site_versions")
    op.drop_table("site_versions")
