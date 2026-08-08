"""add immutable provider route manifests and route request audit

Revision ID: 20260808_0016
Revises: 20260808_0015
Create Date: 2026-08-08 10:10:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260808_0016"
down_revision = "20260808_0015"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_routes (
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          route_version VARCHAR(32) NOT NULL,
          priority INT NOT NULL,
          endpoint_host VARCHAR(255) NOT NULL,
          model_name VARCHAR(160) NOT NULL,
          configuration_fingerprint CHAR(64) NOT NULL,
          is_current TINYINT(1) NOT NULL DEFAULT 1,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (provider_key, route_id, route_version),
          KEY idx_airank_provider_route_current
            (provider_key, is_current, priority, created_at),
          KEY idx_airank_provider_route_fingerprint
            (provider_key, configuration_fingerprint)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    if not _has_column("airank_provider_request_audits", "route_id"):
        op.execute(
            "ALTER TABLE airank_provider_request_audits "
            "ADD COLUMN route_id VARCHAR(64) NULL AFTER provider_key"
        )
    if not _has_index(
        "airank_provider_request_audits", "idx_airank_provider_audit_route"
    ):
        op.execute(
            "CREATE INDEX idx_airank_provider_audit_route "
            "ON airank_provider_request_audits "
            "(provider_key, route_id, requested_at)"
        )


def downgrade() -> None:
    # Route history and request-route attribution are operational audit evidence.
    # Destructive rollback requires an explicit export and migration plan.
    pass
