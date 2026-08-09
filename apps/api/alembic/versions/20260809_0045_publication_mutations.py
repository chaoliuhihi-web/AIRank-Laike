"""add governed publication update and withdrawal lineage

Revision ID: 20260809_0045
Revises: 20260809_0044
Create Date: 2026-08-09 16:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0045"
down_revision = "20260809_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "airank_publish_packages",
        sa.Column(
            "publication_action",
            sa.String(length=16),
            nullable=False,
            server_default="publish",
        ),
    )
    op.add_column(
        "airank_publish_packages",
        sa.Column("target_package_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "airank_publish_packages",
        sa.Column("action_reason", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "airank_publish_packages",
        sa.Column("requested_by", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "idx_airank_publish_package_lineage",
        "airank_publish_packages",
        ["tenant_id", "target_package_id", "publication_action", "created_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_airank_publish_package_target",
        "airank_publish_packages",
        "airank_publish_packages",
        ["target_package_id"],
        ["id"],
    )


def downgrade() -> None:
    # Publication mutation lineage and snapshots are audit evidence. Destructive
    # rollback requires an explicit export and retention decision.
    pass
