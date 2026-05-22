"""media.page_id: ON DELETE CASCADE (SET NULL + NOT NULL page_id -> 1048)

Revision ID: c2a8b1d4e5f2
Revises: a7f3e2b19c04
Create Date: 2026-05-07

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c2a8b1d4e5f2"
down_revision = "a7f3e2b19c04"
branch_labels = None
depends_on = None


def _drop_fk_to_pages(table: str, column: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if fk["referred_table"] != "pages":
            continue
        if list(fk["constrained_columns"]) != [column]:
            continue
        op.drop_constraint(fk["name"], table, type_="foreignkey")
        return
    raise RuntimeError(
        f"Could not find FK on {table}.{column} -> pages.id; "
        "fix manually or adjust migration."
    )


def upgrade() -> None:
    _drop_fk_to_pages("media", "page_id")
    op.create_foreign_key(
        "fk_media_page_id_pages",
        "media",
        "pages",
        ["page_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_media_page_id_pages", "media", type_="foreignkey")
    op.create_foreign_key(
        "fk_media_page_id_pages",
        "media",
        "pages",
        ["page_id"],
        ["id"],
        ondelete="SET NULL",
    )
