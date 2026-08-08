"""add audited provider route control overrides

Revision ID: 20260808_0017
Revises: 20260808_0016
Create Date: 2026-08-08 11:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0017"
down_revision = "20260808_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_route_controls (
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          enabled TINYINT(1) NOT NULL DEFAULT 1,
          priority_override INT NULL,
          control_version BIGINT NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          reason VARCHAR(500) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (provider_key, route_id),
          KEY idx_airank_provider_route_control_enabled
            (provider_key, enabled, priority_override, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_route_control_events (
          id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          control_version BIGINT NOT NULL,
          previous_control_json JSON NULL,
          new_control_json JSON NOT NULL,
          changed_by VARCHAR(128) NOT NULL,
          reason VARCHAR(500) NOT NULL,
          changed_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_route_control_event
            (provider_key, route_id, control_version),
          KEY idx_airank_provider_route_control_event_time
            (provider_key, changed_at, id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Route-control events are operational audit evidence. Destructive rollback
    # requires an explicit export and migration plan.
    pass
