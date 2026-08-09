"""add persistent operation guard for high-risk external side effects

Revision ID: 20260809_0041
Revises: 20260809_0040
Create Date: 2026-08-09 09:25:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0041"
down_revision = "20260809_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_operation_guards (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          operation_type VARCHAR(96) NOT NULL,
          resource_key VARCHAR(255) NOT NULL,
          idempotency_key_sha256 CHAR(64) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          request_key_id VARCHAR(64) NULL,
          state VARCHAR(32) NOT NULL,
          external_effect_started TINYINT(1) NOT NULL DEFAULT 0,
          response_json JSON NULL,
          error_code VARCHAR(96) NULL,
          created_by VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          completed_at DATETIME(3) NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_operation_guard_idempotency
            (tenant_id, operation_type, resource_key, idempotency_key_sha256),
          KEY idx_airank_operation_guard_state
            (tenant_id, state, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_operation_guard_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          operation_id VARCHAR(64) NOT NULL,
          event_sequence INT NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          from_state VARCHAR(32) NULL,
          to_state VARCHAR(32) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_operation_guard_event_sequence
            (operation_id, event_sequence),
          UNIQUE KEY uk_airank_operation_guard_event_hash (event_sha256),
          KEY idx_airank_operation_guard_event_tenant
            (tenant_id, operation_id, event_sequence),
          CONSTRAINT fk_airank_operation_guard_event_operation
            FOREIGN KEY (operation_id) REFERENCES airank_operation_guards (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Operation outcomes and idempotency receipts are security audit evidence.
    # Destructive rollback requires an explicit export and retention decision.
    pass
