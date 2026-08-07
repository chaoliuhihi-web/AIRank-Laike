"""add provider manifest, probe, request, usage, circuit, and quota ledgers

Revision ID: 20260808_0005
Revises: 20260808_0004
Create Date: 2026-08-08 14:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0005"
down_revision = "20260808_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_manifests (
          provider_key VARCHAR(64) NOT NULL,
          manifest_version VARCHAR(32) NOT NULL,
          label VARCHAR(128) NOT NULL,
          implementation_status VARCHAR(32) NOT NULL,
          collection_mode VARCHAR(64) NOT NULL,
          endpoint_host VARCHAR(255) NOT NULL,
          model_name VARCHAR(160) NOT NULL,
          capabilities_json JSON NOT NULL,
          lifecycle_json JSON NULL,
          configuration_fingerprint CHAR(64) NOT NULL,
          is_current TINYINT(1) NOT NULL DEFAULT 1,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (provider_key, manifest_version),
          KEY idx_airank_provider_manifest_current (provider_key, is_current, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_probe_runs (
          id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          probe_level VARCHAR(32) NOT NULL,
          health_state VARCHAR(40) NOT NULL,
          model_name VARCHAR(160) NULL,
          endpoint_host VARCHAR(255) NULL,
          request_id_present TINYINT(1) NOT NULL DEFAULT 0,
          duration_ms INT NOT NULL,
          error_code VARCHAR(80) NULL,
          message VARCHAR(500) NULL,
          checked_at DATETIME(3) NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          KEY idx_airank_provider_probe_latest (provider_key, probe_level, checked_at),
          KEY idx_airank_provider_probe_state (health_state, checked_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_request_audits (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          run_id VARCHAR(64) NULL,
          task_id VARCHAR(64) NULL,
          answer_snapshot_id VARCHAR(64) NULL,
          provider_key VARCHAR(64) NOT NULL,
          model_name VARCHAR(160) NOT NULL,
          endpoint_host VARCHAR(255) NOT NULL,
          configuration_fingerprint CHAR(64) NOT NULL,
          provider_request_id VARCHAR(160) NULL,
          prompt_sha256 CHAR(64) NOT NULL,
          outcome VARCHAR(32) NOT NULL,
          evidence_grade VARCHAR(120) NULL,
          attempt_count INT NOT NULL,
          duration_ms INT NULL,
          error_code VARCHAR(80) NULL,
          provider_error_code VARCHAR(80) NULL,
          requested_at DATETIME(3) NOT NULL,
          completed_at DATETIME(3) NULL,
          metadata_json JSON NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          KEY idx_airank_provider_audit_task (tenant_id, project_id, task_id),
          KEY idx_airank_provider_audit_request (provider_key, provider_request_id),
          KEY idx_airank_provider_audit_outcome (tenant_id, provider_key, outcome, requested_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_usage_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          request_audit_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          model_name VARCHAR(160) NOT NULL,
          input_tokens BIGINT NULL,
          output_tokens BIGINT NULL,
          total_tokens BIGINT NULL,
          precision_status VARCHAR(32) NOT NULL,
          usage_source VARCHAR(80) NOT NULL,
          cost_amount DECIMAL(18,8) NULL,
          cost_currency CHAR(3) NULL,
          price_version VARCHAR(64) NULL,
          occurred_at DATETIME(3) NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_usage_request (tenant_id, request_audit_id),
          KEY idx_airank_provider_usage_rollup (tenant_id, project_id, provider_key, occurred_at),
          CONSTRAINT fk_airank_provider_usage_audit FOREIGN KEY (request_audit_id) REFERENCES airank_provider_request_audits (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_circuit_states (
          provider_key VARCHAR(64) NOT NULL,
          configuration_fingerprint CHAR(64) NOT NULL,
          state VARCHAR(32) NOT NULL,
          consecutive_failures INT NOT NULL DEFAULT 0,
          opened_at DATETIME(3) NULL,
          half_opened_at DATETIME(3) NULL,
          last_success_at DATETIME(3) NULL,
          last_failure_at DATETIME(3) NULL,
          updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
          PRIMARY KEY (provider_key, configuration_fingerprint),
          KEY idx_airank_provider_circuit_state (state, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_quota_buckets (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          period_start DATETIME(3) NOT NULL,
          period_end DATETIME(3) NOT NULL,
          limit_units BIGINT NOT NULL,
          used_units BIGINT NOT NULL DEFAULT 0,
          reserved_units BIGINT NOT NULL DEFAULT 0,
          version_number BIGINT NOT NULL DEFAULT 0,
          updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_quota_period (tenant_id, provider_key, period_start, period_end)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_quota_reservations (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          bucket_id VARCHAR(64) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          units BIGINT NOT NULL,
          status VARCHAR(32) NOT NULL,
          expires_at DATETIME(3) NOT NULL,
          committed_at DATETIME(3) NULL,
          released_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_quota_idempotency (tenant_id, provider_key, idempotency_key),
          KEY idx_airank_provider_quota_expiry (status, expires_at),
          CONSTRAINT fk_airank_provider_quota_bucket FOREIGN KEY (bucket_id) REFERENCES airank_provider_quota_buckets (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Provider requests and usage records are audit evidence. Destructive rollback
    # requires an explicit export/migration rather than silently dropping them.
    pass
