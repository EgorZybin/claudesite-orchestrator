"""

Revision ID: a7f3e2b19c04
Revises: 45059cb11e48
Create Date: 2026-05-07

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7f3e2b19c04"
down_revision = "45059cb11e48"
branch_labels = None
depends_on = None


def _drop_fk_to_pages(table: str, column: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys(table):
        if fk["referred_table"] == "pages" and list(fk["constrained_columns"]) == [
            column
        ]:
            op.drop_constraint(fk["name"], table, type_="foreignkey")
            return
    raise RuntimeError(
        f"Could not find FK on {table}.{column} -> pages.id; "
        "fix manually or adjust migration."
    )


def upgrade() -> None:
    _drop_fk_to_pages("processed_keywords", "page_id")
    op.alter_column(
        "processed_keywords",
        "page_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_processed_keywords_page_id_pages",
        "processed_keywords",
        "pages",
        ["page_id"],
        ["id"],
        ondelete="CASCADE",
    )

    _drop_fk_to_pages("media", "page_id")
    op.alter_column(
        "media",
        "page_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_media_page_id_pages",
        "media",
        "pages",
        ["page_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_media_page_id_pages", "media", type_="foreignkey")
    op.alter_column(
        "media",
        "page_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        None,
        "media",
        "pages",
        ["page_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint(
        "fk_processed_keywords_page_id_pages",
        "processed_keywords",
        type_="foreignkey",
    )
    op.alter_column(
        "processed_keywords",
        "page_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_foreign_key(
        None,
        "processed_keywords",
        "pages",
        ["page_id"],
        ["id"],
        ondelete="SET NULL",
    )
