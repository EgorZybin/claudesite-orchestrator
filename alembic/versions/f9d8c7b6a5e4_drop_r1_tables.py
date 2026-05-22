"""Drop R1 (V1) architecture tables after Phase 15 cleanup.

Removes tables that backed the deleted block-based architecture:
- site_blueprints, site_blueprint_items, site_nav_items — R1 blueprint storage
- site_templates — site-level theme tokens (R1 theme-from-prompt output)
- site_seo_rules — R1 SEO templating
- page_type_presets — R1 default sections per page_type
- processed_keywords — R1 bulk_semantics intake

V2 architecture (per-site Claude-generated templates) uses site_versions +
site_content_blocks + site_modules instead.

Revision ID: f9d8c7b6a5e4
Revises: e2f3a4b5c6d7
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision = "f9d8c7b6a5e4"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


_TABLES_TO_DROP = (
    "site_blueprint_items",
    "site_blueprints",
    "site_nav_items",
    "site_templates",
    "site_seo_rules",
    "page_type_presets",
    "processed_keywords",
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in _TABLES_TO_DROP:
        conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def downgrade() -> None:
    raise RuntimeError(
        "downgrade not supported: V1 tables and SQLAlchemy models removed; "
        "restore from backup if needed."
    )
