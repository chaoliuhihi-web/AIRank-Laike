"""add distributed provider QPS tokens and concurrency leases

Revision ID: 20260808_0015
Revises: 20260808_0014
Create Date: 2026-08-08 09:50:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0015"
down_revision = "20260808_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_capacity_states (
          provider_key VARCHAR(64) NOT NULL,
          configuration_fingerprint CHAR(64) NOT NULL,
          qps_limit INT NOT NULL,
          concurrency_limit INT NOT NULL,
          available_tokens DECIMAL(18,6) NOT NULL,
          last_refill_at DATETIME(3) NOT NULL,
          in_flight_count INT NOT NULL DEFAULT 0,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (provider_key, configuration_fingerprint),
          KEY idx_airank_provider_capacity_updated (updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_capacity_leases (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          configuration_fingerprint CHAR(64) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/released/expired',
          acquired_at DATETIME(3) NOT NULL,
          expires_at DATETIME(3) NOT NULL,
          released_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_capacity_idempotency
            (tenant_id, provider_key, configuration_fingerprint, idempotency_key),
          KEY idx_airank_provider_capacity_expiry
            (provider_key, configuration_fingerprint, status, expires_at),
          KEY idx_airank_provider_capacity_project
            (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_provider_capacity_state
            FOREIGN KEY (provider_key, configuration_fingerprint)
            REFERENCES airank_provider_capacity_states
              (provider_key, configuration_fingerprint)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Capacity leases are operational audit evidence. Destructive rollback
    # requires an explicit drain/export plan rather than silently dropping them.
    pass
