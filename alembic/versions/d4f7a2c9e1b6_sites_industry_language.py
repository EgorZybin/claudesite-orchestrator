"""Add industry and language columns to sites.

Adds two columns previously missing from the Site model:
- `industry` (VARCHAR(64), nullable) — domain identifier (legal/medical/saas/...)
  used at render time for conditional template logic (e.g. top-bar in nav).
- `language` (VARCHAR(8), NOT NULL, default 'ru') — ISO 639-1 site language for
  <html lang="..."> and rendering decisions.

Previously both lived only in `SiteContent.site_meta` (transient — discarded after
generation). The renderer hardcoded `industry='unknown'` and `language='ru'`,
which broke industry-conditional template logic Claude relies on (top-bar
conditional, JSON-LD type selection, etc.).

`persist.py` now writes these from `site_meta` on every generation; `public.py`
reads them when building the render context.

Revision ID: d4f7a2c9e1b6
Revises: f9d8c7b6a5e4
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d4f7a2c9e1b6"
down_revision = "f9d8c7b6a5e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sites",
        sa.Column("industry", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "sites",
        sa.Column(
            "language",
            sa.String(length=8),
            nullable=False,
            server_default="ru",
        ),
    )


def downgrade() -> None:
    op.drop_column("sites", "language")
    op.drop_column("sites", "industry")
