"""add content review, immutable publishing snapshots, and retest windows

Revision ID: 20260808_0007
Revises: 20260808_0006
Create Date: 2026-08-08 16:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0007"
down_revision = "20260808_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE airank_content_assets ADD COLUMN content_sha256 CHAR(64) NULL AFTER body_md")
    op.execute("CREATE INDEX idx_airank_content_asset_hash ON airank_content_assets (tenant_id, project_id, content_sha256)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_content_reviews (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          asset_id VARCHAR(64) NOT NULL,
          content_sha256 CHAR(64) NOT NULL,
          action VARCHAR(32) NOT NULL,
          fact_check_status VARCHAR(32) NOT NULL,
          risk_level VARCHAR(32) NOT NULL,
          risk_findings_json JSON NOT NULL,
          override_reason TEXT NULL,
          reviewed_by VARCHAR(64) NOT NULL,
          review_note TEXT NULL,
          reviewed_at DATETIME(3) NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          KEY idx_airank_content_review_asset (tenant_id, project_id, asset_id, reviewed_at),
          KEY idx_airank_content_review_status (tenant_id, action, fact_check_status, risk_level),
          CONSTRAINT fk_airank_content_review_asset FOREIGN KEY (asset_id) REFERENCES airank_content_assets (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_publish_snapshots (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          asset_id VARCHAR(64) NOT NULL,
          content_review_id VARCHAR(64) NOT NULL,
          snapshot_version INT NOT NULL,
          title VARCHAR(255) NOT NULL,
          body_md MEDIUMTEXT NOT NULL,
          content_sha256 CHAR(64) NOT NULL,
          manifest_json JSON NOT NULL,
          created_by VARCHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_publish_snapshot_version (tenant_id, asset_id, snapshot_version),
          KEY idx_airank_publish_snapshot_hash (tenant_id, project_id, content_sha256),
          CONSTRAINT fk_airank_publish_snapshot_asset FOREIGN KEY (asset_id) REFERENCES airank_content_assets (id),
          CONSTRAINT fk_airank_publish_snapshot_review FOREIGN KEY (content_review_id) REFERENCES airank_content_reviews (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute("ALTER TABLE airank_publish_packages ADD COLUMN snapshot_id VARCHAR(64) NULL AFTER asset_id")
    op.execute("ALTER TABLE airank_publish_packages ADD COLUMN content_review_id VARCHAR(64) NULL AFTER snapshot_id")
    op.execute("ALTER TABLE airank_publish_packages ADD COLUMN idempotency_key VARCHAR(160) NULL AFTER content_review_id")
    op.execute("ALTER TABLE airank_publish_packages ADD UNIQUE KEY uk_airank_publish_idempotency (tenant_id, project_id, idempotency_key)")
    op.execute("ALTER TABLE airank_publish_packages ADD CONSTRAINT fk_airank_publish_snapshot FOREIGN KEY (snapshot_id) REFERENCES airank_publish_snapshots (id)")
    op.execute("ALTER TABLE airank_publish_packages ADD CONSTRAINT fk_airank_publish_review FOREIGN KEY (content_review_id) REFERENCES airank_content_reviews (id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_publish_attempts (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          package_id VARCHAR(64) NOT NULL,
          attempt_number INT NOT NULL,
          channel VARCHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          response_status INT NULL,
          response_sha256 CHAR(64) NULL,
          error_code VARCHAR(80) NULL,
          error_message VARCHAR(1000) NULL,
          started_at DATETIME(3) NOT NULL,
          finished_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_publish_attempt_number (tenant_id, package_id, attempt_number),
          KEY idx_airank_publish_attempt_status (tenant_id, project_id, status, started_at),
          CONSTRAINT fk_airank_publish_attempt_package FOREIGN KEY (package_id) REFERENCES airank_publish_packages (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_retest_observation_windows (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          package_id VARCHAR(64) NOT NULL,
          baseline_run_id VARCHAR(64) NULL,
          window_label VARCHAR(16) NOT NULL,
          due_at DATETIME(3) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
          compare_run_id VARCHAR(64) NULL,
          result_json JSON NULL,
          completed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_retest_window (tenant_id, package_id, window_label),
          KEY idx_airank_retest_window_due (status, due_at),
          CONSTRAINT fk_airank_retest_window_package FOREIGN KEY (package_id) REFERENCES airank_publish_packages (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Review and publication snapshots are immutable audit records. Destructive
    # rollback requires an explicit export/migration.
    pass
