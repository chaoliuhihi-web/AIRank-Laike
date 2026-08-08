"""add governed knowledge source synchronization

Revision ID: 20260808_0024
Revises: 20260808_0023
Create Date: 2026-08-08 23:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0024"
down_revision = "20260808_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_knowledge_sync_policies (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          anchor_source_id VARCHAR(64) NOT NULL,
          current_source_id VARCHAR(64) NOT NULL,
          source_uri VARCHAR(2048) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          interval_hours INT NOT NULL,
          enabled TINYINT(1) NOT NULL DEFAULT 1,
          version INT NOT NULL DEFAULT 1,
          next_run_at DATETIME(3) NOT NULL,
          last_run_id VARCHAR(64) NULL,
          last_status VARCHAR(32) NULL,
          last_checked_at DATETIME(3) NULL,
          created_by VARCHAR(64) NOT NULL,
          updated_by VARCHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_knowledge_sync_anchor (tenant_id, project_id, anchor_source_id),
          UNIQUE KEY uk_airank_knowledge_sync_idempotency (tenant_id, project_id, idempotency_key),
          KEY idx_airank_knowledge_sync_due (enabled, next_run_at, tenant_id, project_id),
          KEY idx_airank_knowledge_sync_current (tenant_id, project_id, current_source_id),
          CONSTRAINT fk_airank_knowledge_sync_project FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_knowledge_sync_anchor FOREIGN KEY (anchor_source_id) REFERENCES airank_knowledge_sources (id),
          CONSTRAINT fk_airank_knowledge_sync_current FOREIGN KEY (current_source_id) REFERENCES airank_knowledge_sources (id),
          CONSTRAINT chk_airank_knowledge_sync_interval CHECK (interval_hours BETWEEN 1 AND 720)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_knowledge_sync_runs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          policy_id VARCHAR(64) NOT NULL,
          source_before_id VARCHAR(64) NOT NULL,
          source_after_id VARCHAR(64) NULL,
          job_id VARCHAR(64) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'queued',
          requested_url VARCHAR(2048) NOT NULL,
          final_url VARCHAR(2048) NULL,
          evidence_grade VARCHAR(64) NULL,
          response_status INT NULL,
          content_type VARCHAR(128) NULL,
          response_bytes BIGINT NULL,
          raw_content_sha256 CHAR(64) NULL,
          visible_text_sha256 CHAR(64) NULL,
          raw_object_ref_id VARCHAR(64) NULL,
          text_object_ref_id VARCHAR(64) NULL,
          connected_ip VARCHAR(64) NULL,
          redirect_count INT NULL,
          error_code VARCHAR(128) NULL,
          error_message VARCHAR(1000) NULL,
          scheduled_at DATETIME(3) NOT NULL,
          started_at DATETIME(3) NULL,
          completed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_knowledge_sync_job (tenant_id, job_id),
          UNIQUE KEY uk_airank_knowledge_sync_idempotency (tenant_id, project_id, policy_id, idempotency_key),
          KEY idx_airank_knowledge_sync_run_policy (tenant_id, project_id, policy_id, scheduled_at),
          KEY idx_airank_knowledge_sync_run_status (tenant_id, project_id, status, scheduled_at),
          CONSTRAINT fk_airank_knowledge_sync_run_project FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_knowledge_sync_run_policy FOREIGN KEY (policy_id) REFERENCES airank_knowledge_sync_policies (id),
          CONSTRAINT fk_airank_knowledge_sync_run_before FOREIGN KEY (source_before_id) REFERENCES airank_knowledge_sources (id),
          CONSTRAINT fk_airank_knowledge_sync_run_after FOREIGN KEY (source_after_id) REFERENCES airank_knowledge_sources (id),
          CONSTRAINT fk_airank_knowledge_sync_run_job FOREIGN KEY (job_id) REFERENCES airank_async_jobs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Sync runs are immutable evidence of source changes. Export them before any
    # deliberate destructive rollback instead of silently dropping history.
    pass
