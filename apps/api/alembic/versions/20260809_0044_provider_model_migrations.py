"""add governed Provider model migration plans and immutable events

Revision ID: 20260809_0044
Revises: 20260809_0043
Create Date: 2026-08-09 14:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0044"
down_revision = "20260809_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_model_migrations (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          from_model VARCHAR(160) NOT NULL,
          to_model VARCHAR(160) NOT NULL,
          from_configuration_fingerprint CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL,
          plan_version INT NOT NULL,
          validation_request_audit_id VARCHAR(64) NULL,
          validation_provider_request_id VARCHAR(160) NULL,
          validation_configuration_fingerprint CHAR(64) NULL,
          validation_requested_at DATETIME(3) NULL,
          idempotency_key_sha256 CHAR(64) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          reason VARCHAR(500) NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          validated_by VARCHAR(128) NULL,
          approved_by VARCHAR(128) NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          validated_at DATETIME(3) NULL,
          approved_at DATETIME(3) NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_model_migration_basis
            (tenant_id, provider_key, route_id, from_configuration_fingerprint),
          UNIQUE KEY uk_airank_provider_model_migration_idempotency
            (tenant_id, idempotency_key_sha256),
          KEY idx_airank_provider_model_migration_status
            (tenant_id, status, updated_at),
          KEY idx_airank_provider_model_migration_validation
            (tenant_id, validation_request_audit_id),
          CONSTRAINT fk_airank_provider_model_migration_audit
            FOREIGN KEY (validation_request_audit_id)
            REFERENCES airank_provider_request_audits (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_model_migration_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          migration_id VARCHAR(64) NOT NULL,
          event_sequence INT NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          from_status VARCHAR(32) NULL,
          to_status VARCHAR(32) NOT NULL,
          plan_version INT NOT NULL,
          request_audit_id VARCHAR(64) NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor VARCHAR(128) NOT NULL,
          reason VARCHAR(500) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_model_migration_event
            (tenant_id, migration_id, event_sequence),
          KEY idx_airank_provider_model_migration_event_time
            (tenant_id, created_at),
          CONSTRAINT fk_airank_provider_model_migration_event_plan
            FOREIGN KEY (migration_id)
            REFERENCES airank_provider_model_migrations (id),
          CONSTRAINT fk_airank_provider_model_migration_event_audit
            FOREIGN KEY (request_audit_id)
            REFERENCES airank_provider_request_audits (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Migration plans and their hash-chained events are audit evidence.
    # Destructive rollback requires an explicit export and retention decision.
    pass
