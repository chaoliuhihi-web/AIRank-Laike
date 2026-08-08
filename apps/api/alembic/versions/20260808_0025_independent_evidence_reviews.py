"""add independent evidence review cases and agreement gates

Revision ID: 20260808_0025
Revises: 20260808_0024
Create Date: 2026-08-09 00:20:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0025"
down_revision = "20260808_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_review_cases (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          snapshot_id VARCHAR(64) NOT NULL,
          review_kind VARCHAR(32) NOT NULL COMMENT 'citation_support/fact_accuracy',
          target_key CHAR(64) NOT NULL,
          claim_id VARCHAR(64) NOT NULL,
          citation_id VARCHAR(64) NULL,
          evidence_basis_sha256 CHAR(64) NOT NULL,
          purpose VARCHAR(32) NOT NULL DEFAULT 'production' COMMENT 'production/benchmark',
          benchmark_version VARCHAR(64) NULL,
          status VARCHAR(32) NOT NULL COMMENT 'creating/awaiting_secondary/disputed/agreed/adjudicated/void',
          consensus_label VARCHAR(32) NULL,
          primary_review_id VARCHAR(64) NULL,
          secondary_review_id VARCHAR(64) NULL,
          adjudication_review_id VARCHAR(64) NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(64) NOT NULL,
          finalized_by VARCHAR(64) NULL,
          created_at DATETIME(3) NOT NULL,
          finalized_at DATETIME(3) NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_evidence_review_case_idempotency
            (tenant_id, project_id, idempotency_key),
          UNIQUE KEY uk_airank_evidence_review_case_basis
            (tenant_id, project_id, review_kind, target_key, evidence_basis_sha256, purpose),
          KEY idx_airank_evidence_review_queue
            (tenant_id, project_id, status, review_kind, created_at),
          KEY idx_airank_evidence_review_snapshot
            (tenant_id, project_id, snapshot_id, created_at),
          CONSTRAINT fk_airank_evidence_review_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_evidence_review_snapshot
            FOREIGN KEY (snapshot_id) REFERENCES airank_answer_snapshots (id),
          CONSTRAINT fk_airank_evidence_review_claim
            FOREIGN KEY (claim_id) REFERENCES airank_answer_claims (id),
          CONSTRAINT fk_airank_evidence_review_citation
            FOREIGN KEY (citation_id) REFERENCES airank_source_citations (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        "ALTER TABLE airank_citation_support_reviews "
        "ADD COLUMN review_case_id VARCHAR(64) NULL AFTER reviewed_at"
    )
    op.execute(
        "ALTER TABLE airank_citation_support_reviews "
        "ADD COLUMN reviewer_role VARCHAR(32) NOT NULL DEFAULT 'single' AFTER review_case_id"
    )
    op.execute(
        "CREATE INDEX idx_airank_citation_support_case "
        "ON airank_citation_support_reviews (tenant_id, review_case_id, reviewer_role, reviewed_at)"
    )
    op.execute(
        "ALTER TABLE airank_citation_support_reviews "
        "ADD CONSTRAINT fk_airank_citation_support_case "
        "FOREIGN KEY (review_case_id) REFERENCES airank_evidence_review_cases (id)"
    )
    op.execute(
        "ALTER TABLE airank_fact_accuracy_reviews "
        "ADD COLUMN review_case_id VARCHAR(64) NULL AFTER reviewed_at"
    )
    op.execute(
        "ALTER TABLE airank_fact_accuracy_reviews "
        "ADD COLUMN reviewer_role VARCHAR(32) NOT NULL DEFAULT 'single' AFTER review_case_id"
    )
    op.execute(
        "CREATE INDEX idx_airank_fact_accuracy_case "
        "ON airank_fact_accuracy_reviews (tenant_id, review_case_id, reviewer_role, reviewed_at)"
    )
    op.execute(
        "ALTER TABLE airank_fact_accuracy_reviews "
        "ADD CONSTRAINT fk_airank_fact_accuracy_case "
        "FOREIGN KEY (review_case_id) REFERENCES airank_evidence_review_cases (id)"
    )


def downgrade() -> None:
    # Review cases and their independent decisions are customer evidence.
    # Export them before any deliberate destructive rollback.
    pass
