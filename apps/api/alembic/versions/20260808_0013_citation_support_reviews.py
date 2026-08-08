"""add answer claims and append-only citation support reviews

Revision ID: 20260808_0013
Revises: 20260808_0012
Create Date: 2026-08-08 11:40:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0013"
down_revision = "20260808_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_answer_claims (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          snapshot_id VARCHAR(64) NOT NULL,
          claim_text TEXT NOT NULL,
          answer_start INT NOT NULL,
          answer_end INT NOT NULL,
          answer_sha256 CHAR(64) NOT NULL,
          claim_sha256 CHAR(64) NOT NULL,
          extraction_method VARCHAR(32) NOT NULL COMMENT 'manual/ai_assisted',
          extractor_version VARCHAR(64) NOT NULL,
          created_by VARCHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_answer_claim_boundary
            (tenant_id, snapshot_id, answer_start, answer_end, claim_sha256),
          KEY idx_airank_answer_claim_project (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_answer_claim_snapshot
            FOREIGN KEY (snapshot_id) REFERENCES airank_answer_snapshots (id),
          CONSTRAINT fk_airank_answer_claim_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_citation_support_reviews (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          claim_id VARCHAR(64) NOT NULL,
          citation_id VARCHAR(64) NOT NULL,
          support_label VARCHAR(32) NOT NULL COMMENT 'supports/contradicts/insufficient',
          evidence_grade VARCHAR(64) NOT NULL COMMENT 'provider_excerpt_only/source_panel_capture/source_page_snapshot',
          source_excerpt TEXT NOT NULL,
          source_content_sha256 CHAR(64) NOT NULL,
          source_object_ref_id VARCHAR(64) NULL,
          rationale TEXT NOT NULL,
          review_method VARCHAR(32) NOT NULL COMMENT 'human/ai_assisted',
          reviewed_by VARCHAR(64) NOT NULL,
          reviewed_at DATETIME(3) NOT NULL,
          supersedes_review_id VARCHAR(64) NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          KEY idx_airank_citation_support_claim
            (tenant_id, claim_id, citation_id, reviewed_at),
          KEY idx_airank_citation_support_project
            (tenant_id, project_id, evidence_grade, reviewed_at),
          CONSTRAINT fk_airank_citation_support_claim
            FOREIGN KEY (claim_id) REFERENCES airank_answer_claims (id),
          CONSTRAINT fk_airank_citation_support_citation
            FOREIGN KEY (citation_id) REFERENCES airank_source_citations (id),
          CONSTRAINT fk_airank_citation_support_source_object
            FOREIGN KEY (source_object_ref_id) REFERENCES airank_object_refs (id),
          CONSTRAINT fk_airank_citation_support_supersedes
            FOREIGN KEY (supersedes_review_id) REFERENCES airank_citation_support_reviews (id),
          CONSTRAINT fk_airank_citation_support_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Citation support reviews are customer evidence. Destructive downgrade
    # requires an explicit export and migration plan.
    pass
