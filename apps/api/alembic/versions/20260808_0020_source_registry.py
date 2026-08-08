"""add versioned citation source registry reviews

Revision ID: 20260808_0020
Revises: 20260808_0019
Create Date: 2026-08-08 17:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0020"
down_revision = "20260808_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_source_classification_revisions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          normalized_host VARCHAR(253) NOT NULL,
          revision_number INT NOT NULL,
          source_category_l1 VARCHAR(64) NOT NULL,
          source_type VARCHAR(96) NOT NULL,
          ecosystem VARCHAR(160) NULL,
          classification_status VARCHAR(32) NOT NULL COMMENT 'reviewed/curated',
          classification_method VARCHAR(32) NOT NULL COMMENT 'human_review/dataset_import',
          classification_confidence VARCHAR(16) NOT NULL COMMENT 'low/medium/high',
          authority_level VARCHAR(16) NOT NULL COMMENT 'unknown/low/medium/high/official',
          usage_policy VARCHAR(32) NOT NULL COMMENT 'primary_evidence/context_only/lead_only/prohibited',
          risk_level VARCHAR(16) NOT NULL COMMENT 'low/medium/high/critical',
          evidence_note TEXT NOT NULL,
          evidence_url VARCHAR(2048) NULL,
          source_dataset_name VARCHAR(160) NULL,
          source_dataset_version VARCHAR(64) NULL,
          valid_until DATETIME(3) NULL,
          reviewed_by VARCHAR(64) NOT NULL,
          reviewed_at DATETIME(3) NOT NULL,
          supersedes_revision_id VARCHAR(64) NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_source_classification_version
            (tenant_id, project_id, normalized_host, revision_number),
          UNIQUE KEY uk_airank_source_classification_idempotency
            (tenant_id, idempotency_key),
          KEY idx_airank_source_classification_current
            (tenant_id, project_id, normalized_host, revision_number),
          KEY idx_airank_source_classification_governance
            (tenant_id, project_id, classification_status, authority_level, usage_policy),
          CONSTRAINT fk_airank_source_classification_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_source_classification_supersedes
            FOREIGN KEY (supersedes_revision_id)
              REFERENCES airank_source_classification_revisions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Source reviews are append-only customer evidence. Destructive rollback
    # requires an explicit export and migration plan.
    pass
