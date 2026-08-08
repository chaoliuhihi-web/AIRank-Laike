"""add governed answer fact classifications and immutable accuracy reviews

Revision ID: 20260808_0019
Revises: 20260808_0018
Create Date: 2026-08-08 12:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0019"
down_revision = "20260808_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE airank_answer_claims "
        "ADD COLUMN claim_kind VARCHAR(32) NOT NULL DEFAULT 'unclassified' "
        "AFTER extractor_version"
    )
    op.execute(
        "ALTER TABLE airank_answer_claims "
        "ADD COLUMN subject_entity_text VARCHAR(512) NULL AFTER claim_kind"
    )
    op.execute("ALTER TABLE airank_answer_claims DROP INDEX uk_airank_answer_claim_boundary")
    op.execute(
        "ALTER TABLE airank_answer_claims "
        "ADD UNIQUE KEY uk_airank_answer_claim_boundary "
        "(tenant_id, snapshot_id, answer_start, answer_end, claim_sha256, claim_kind)"
    )
    op.execute(
        "CREATE INDEX idx_airank_answer_claim_fact_kind "
        "ON airank_answer_claims (tenant_id, project_id, claim_kind, created_at)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_fact_accuracy_reviews (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          claim_id VARCHAR(64) NOT NULL,
          verdict VARCHAR(32) NOT NULL COMMENT 'accurate/inaccurate/outdated/insufficient_evidence',
          evidence_grade VARCHAR(64) NOT NULL COMMENT 'approved_fact_source_boundary/no_approved_fact',
          fact_revision_id VARCHAR(64) NULL,
          knowledge_source_id VARCHAR(64) NULL,
          knowledge_segment_id VARCHAR(64) NULL,
          fact_revision_sha256 CHAR(64) NULL,
          source_content_sha256 CHAR(64) NULL,
          quoted_text TEXT NULL,
          quoted_text_sha256 CHAR(64) NULL,
          source_start INT NULL,
          source_end INT NULL,
          rationale TEXT NOT NULL,
          review_method VARCHAR(32) NOT NULL COMMENT 'human/ai_assisted',
          reviewed_by VARCHAR(64) NOT NULL,
          reviewed_at DATETIME(3) NOT NULL,
          supersedes_review_id VARCHAR(64) NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_fact_accuracy_idempotency
            (tenant_id, idempotency_key),
          KEY idx_airank_fact_accuracy_claim
            (tenant_id, claim_id, reviewed_at, id),
          KEY idx_airank_fact_accuracy_project
            (tenant_id, project_id, verdict, reviewed_at),
          CONSTRAINT fk_airank_fact_accuracy_claim
            FOREIGN KEY (claim_id) REFERENCES airank_answer_claims (id),
          CONSTRAINT fk_airank_fact_accuracy_revision
            FOREIGN KEY (fact_revision_id) REFERENCES airank_fact_revisions (id),
          CONSTRAINT fk_airank_fact_accuracy_source
            FOREIGN KEY (knowledge_source_id) REFERENCES airank_knowledge_sources (id),
          CONSTRAINT fk_airank_fact_accuracy_segment
            FOREIGN KEY (knowledge_segment_id) REFERENCES airank_knowledge_segments (id),
          CONSTRAINT fk_airank_fact_accuracy_supersedes
            FOREIGN KEY (supersedes_review_id) REFERENCES airank_fact_accuracy_reviews (id),
          CONSTRAINT fk_airank_fact_accuracy_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Accuracy reviews are customer evidence. Destructive rollback requires an
    # explicit evidence export and migration plan.
    pass
