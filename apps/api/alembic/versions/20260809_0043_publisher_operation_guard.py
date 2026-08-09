"""bind external publishing to the persistent Operation Guard

Revision ID: 20260809_0043
Revises: 20260809_0042
Create Date: 2026-08-09 12:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260809_0043"
down_revision = "20260809_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "airank_publish_attempts",
        sa.Column("operation_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uk_airank_publish_attempt_operation",
        "airank_publish_attempts",
        ["operation_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_airank_publish_attempt_operation",
        "airank_publish_attempts",
        "airank_operation_guards",
        ["operation_id"],
        ["id"],
    )


def downgrade() -> None:
    # Publish attempts and operation events are audit evidence. Destructive
    # rollback requires an explicit export and retention decision.
    pass
