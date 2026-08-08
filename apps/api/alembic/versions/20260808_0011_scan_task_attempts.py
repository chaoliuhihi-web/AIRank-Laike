"""add immutable scan task attempt ledger

Revision ID: 20260808_0011
Revises: 20260808_0010
Create Date: 2026-08-08 23:55:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0011"
down_revision = "20260808_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_scan_task_attempts (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          run_id VARCHAR(64) NOT NULL,
          task_id VARCHAR(64) NOT NULL,
          job_id VARCHAR(64) NOT NULL,
          attempt_number INT NOT NULL,
          provider VARCHAR(64) NOT NULL,
          collector_surface VARCHAR(32) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'running/succeeded/failed/blocked/unknown/suppressed',
          answer_snapshot_id VARCHAR(64) NULL,
          evidence_snapshot_id VARCHAR(64) NULL,
          provider_request_id VARCHAR(128) NULL,
          error_code VARCHAR(128) NULL,
          error_message TEXT NULL,
          metadata_json JSON NULL,
          started_at DATETIME(3) NOT NULL,
          completed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_scan_attempt_number (tenant_id, task_id, attempt_number),
          KEY idx_airank_scan_attempt_run (tenant_id, project_id, run_id, status),
          KEY idx_airank_scan_attempt_job (tenant_id, job_id),
          CONSTRAINT fk_airank_scan_attempt_task FOREIGN KEY (task_id) REFERENCES airank_scan_tasks (id),
          CONSTRAINT fk_airank_scan_attempt_job FOREIGN KEY (job_id) REFERENCES airank_async_jobs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Attempt history is audit evidence. Destructive downgrade is intentionally
    # disabled and requires an explicit export/migration.
    pass
