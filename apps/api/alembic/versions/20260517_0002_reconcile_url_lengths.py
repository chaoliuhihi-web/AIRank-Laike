"""reconcile URL column lengths with API contracts

Revision ID: 20260517_0002
Revises: 20260517_0001
Create Date: 2026-05-17 21:15:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260517_0002"
down_revision = "20260517_0001"
branch_labels = None
depends_on = None


URL_COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("airank_projects", "website_url", False),
    ("airank_competitors", "website_url", False),
    ("airank_source_citations", "url", False),
    ("airank_fact_sources", "source_url", False),
    ("airank_content_assets", "target_url", False),
    ("airank_publish_packages", "published_url", False),
    ("airank_object_refs", "object_uri", True),
)


def upgrade() -> None:
    for table_name, column_name, required in URL_COLUMNS:
        nullability = "NOT NULL" if required else "NULL"
        op.execute(
            f"ALTER TABLE {table_name} "
            f"MODIFY COLUMN {column_name} VARCHAR(2048) {nullability}"
        )


def downgrade() -> None:
    # Do not shrink URL fields; existing 2048-character values could be truncated.
    pass
