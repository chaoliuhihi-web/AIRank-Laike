"""add immutable page extractability audit runs and findings

Revision ID: 20260808_0012
Revises: 20260808_0011
Create Date: 2026-08-08 09:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0012"
down_revision = "20260808_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_page_audit_runs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          job_id VARCHAR(64) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          requested_url VARCHAR(2048) NOT NULL,
          final_url VARCHAR(2048) NULL,
          status VARCHAR(32) NOT NULL COMMENT 'queued/running/completed/blocked/failed',
          rules_version VARCHAR(64) NOT NULL,
          evidence_grade VARCHAR(64) NULL,
          technical_extractability_score INT NULL,
          response_status INT NULL,
          response_content_type VARCHAR(255) NULL,
          response_bytes BIGINT NULL,
          content_sha256 CHAR(64) NULL,
          connected_ip VARCHAR(64) NULL,
          redirect_count INT NULL,
          extracted_json JSON NULL,
          error_code VARCHAR(128) NULL,
          error_message TEXT NULL,
          requested_by VARCHAR(64) NOT NULL,
          started_at DATETIME(3) NULL,
          completed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_page_audit_idempotency (tenant_id, project_id, idempotency_key),
          UNIQUE KEY uk_airank_page_audit_job (tenant_id, job_id),
          KEY idx_airank_page_audit_project (tenant_id, project_id, created_at),
          KEY idx_airank_page_audit_status (status, updated_at),
          CONSTRAINT fk_airank_page_audit_project FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_page_audit_job FOREIGN KEY (job_id) REFERENCES airank_async_jobs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_page_audit_findings (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          run_id VARCHAR(64) NOT NULL,
          rule_id VARCHAR(128) NOT NULL,
          severity VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL,
          title VARCHAR(255) NOT NULL,
          description TEXT NOT NULL,
          recommendation TEXT NULL,
          evidence_json JSON NOT NULL,
          score_delta INT NOT NULL DEFAULT 0,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_page_audit_rule (tenant_id, run_id, rule_id),
          KEY idx_airank_page_audit_finding_project (tenant_id, project_id, severity, status),
          CONSTRAINT fk_airank_page_audit_finding_run FOREIGN KEY (run_id) REFERENCES airank_page_audit_runs (id),
          CONSTRAINT fk_airank_page_audit_finding_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Page audit runs are customer evidence. Destructive downgrade requires an
    # explicit export and migration plan.
    pass
