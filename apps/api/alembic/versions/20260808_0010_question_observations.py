"""add immutable buyer-query observation batches and records

Revision ID: 20260808_0010
Revises: 20260808_0009
Create Date: 2026-08-08 21:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0010"
down_revision = "20260808_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_question_observation_batches (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          source_type VARCHAR(64) NOT NULL,
          source_name VARCHAR(255) NOT NULL,
          access_mode VARCHAR(32) NOT NULL,
          evidence_grade VARCHAR(64) NOT NULL,
          source_uri VARCHAR(2048) NULL,
          date_range_start DATETIME(3) NULL,
          date_range_end DATETIME(3) NULL,
          payload_sha256 CHAR(64) NOT NULL,
          manifest_json JSON NOT NULL,
          record_count INT NOT NULL,
          occurrence_count BIGINT NOT NULL,
          pii_blocked_count INT NOT NULL DEFAULT 0,
          status VARCHAR(32) NOT NULL,
          rights_attested TINYINT(1) NOT NULL DEFAULT 0,
          imported_by VARCHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_question_observation_payload (tenant_id, project_id, payload_sha256),
          KEY idx_airank_question_observation_project (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_question_observation_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_question_observations (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          batch_id VARCHAR(64) NOT NULL,
          source_row_number INT NOT NULL,
          source_record_id VARCHAR(255) NOT NULL,
          question_text TEXT NOT NULL,
          normalized_question_text TEXT NOT NULL,
          dedupe_sha256 CHAR(64) NOT NULL,
          occurrence_count INT NOT NULL,
          observed_at DATETIME(3) NULL,
          region VARCHAR(128) NULL,
          audience_role VARCHAR(128) NULL,
          content_sha256 CHAR(64) NOT NULL,
          pii_status VARCHAR(32) NOT NULL DEFAULT 'none_detected',
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_question_observation_row (tenant_id, batch_id, source_row_number),
          UNIQUE KEY uk_airank_question_observation_source_record (tenant_id, batch_id, source_record_id),
          KEY idx_airank_question_observation_dedupe (tenant_id, project_id, dedupe_sha256),
          CONSTRAINT fk_airank_question_observation_batch
            FOREIGN KEY (batch_id) REFERENCES airank_question_observation_batches (id),
          CONSTRAINT fk_airank_question_observation_record_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Observation snapshots are audit evidence. Destructive downgrade requires export/migration.
    pass
