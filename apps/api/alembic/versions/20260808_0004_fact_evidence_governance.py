"""add governed fact revisions, conflicts, claims, and supports

Revision ID: 20260808_0004
Revises: 20260808_0003
Create Date: 2026-08-08 13:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0004"
down_revision = "20260808_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_knowledge_sources (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          parent_source_id VARCHAR(64) NULL,
          source_type VARCHAR(64) NOT NULL,
          title VARCHAR(512) NOT NULL,
          source_uri VARCHAR(2048) NOT NULL,
          object_ref_id VARCHAR(64) NULL,
          content_sha256 CHAR(64) NOT NULL,
          authority_level VARCHAR(32) NOT NULL DEFAULT 'unclassified',
          risk_level VARCHAR(32) NOT NULL DEFAULT 'medium',
          status VARCHAR(32) NOT NULL DEFAULT 'active',
          revision_number INT NOT NULL,
          captured_at DATETIME(3) NOT NULL,
          valid_from DATETIME(3) NULL,
          valid_until DATETIME(3) NULL,
          metadata_json JSON NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_knowledge_source_revision (tenant_id, project_id, source_uri(512), revision_number),
          KEY idx_airank_knowledge_source_hash (tenant_id, project_id, content_sha256),
          KEY idx_airank_knowledge_source_status (tenant_id, project_id, status, valid_until),
          CONSTRAINT fk_airank_knowledge_source_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_fact_revisions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          fact_atom_id VARCHAR(64) NOT NULL,
          revision_number INT NOT NULL,
          fact_text TEXT NOT NULL,
          content_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'proposed',
          source_ids_json JSON NOT NULL,
          valid_from DATETIME(3) NULL,
          valid_until DATETIME(3) NULL,
          created_by VARCHAR(64) NOT NULL,
          reviewed_by VARCHAR(64) NULL,
          reviewed_at DATETIME(3) NULL,
          review_note TEXT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_fact_revision_number (tenant_id, fact_atom_id, revision_number),
          KEY idx_airank_fact_revision_status (tenant_id, project_id, status, valid_until),
          KEY idx_airank_fact_revision_hash (tenant_id, project_id, content_sha256),
          CONSTRAINT fk_airank_fact_revision_fact FOREIGN KEY (fact_atom_id) REFERENCES airank_fact_atoms (id),
          CONSTRAINT fk_airank_fact_revision_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_fact_conflicts (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          fact_atom_id VARCHAR(64) NOT NULL,
          left_revision_id VARCHAR(64) NOT NULL,
          right_revision_id VARCHAR(64) NOT NULL,
          conflict_type VARCHAR(64) NOT NULL,
          description TEXT NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'open',
          detected_at DATETIME(3) NOT NULL,
          resolved_by VARCHAR(64) NULL,
          resolved_at DATETIME(3) NULL,
          resolution_note TEXT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_fact_conflict_pair (tenant_id, fact_atom_id, left_revision_id, right_revision_id),
          KEY idx_airank_fact_conflict_open (tenant_id, project_id, status, detected_at),
          CONSTRAINT fk_airank_fact_conflict_fact FOREIGN KEY (fact_atom_id) REFERENCES airank_fact_atoms (id),
          CONSTRAINT fk_airank_fact_conflict_left FOREIGN KEY (left_revision_id) REFERENCES airank_fact_revisions (id),
          CONSTRAINT fk_airank_fact_conflict_right FOREIGN KEY (right_revision_id) REFERENCES airank_fact_revisions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_claim_assertions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          asset_id VARCHAR(64) NULL,
          claim_text TEXT NOT NULL,
          claim_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          verified_by VARCHAR(64) NULL,
          verified_at DATETIME(3) NULL,
          metadata_json JSON NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          KEY idx_airank_claim_asset (tenant_id, project_id, asset_id, status),
          KEY idx_airank_claim_hash (tenant_id, project_id, claim_sha256),
          CONSTRAINT fk_airank_claim_project FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_claim_asset FOREIGN KEY (asset_id) REFERENCES airank_content_assets (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_claim_supports (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          assertion_id VARCHAR(64) NOT NULL,
          fact_revision_id VARCHAR(64) NOT NULL,
          knowledge_source_id VARCHAR(64) NOT NULL,
          support_type VARCHAR(32) NOT NULL,
          quoted_text TEXT NOT NULL,
          source_start INT NOT NULL,
          source_end INT NOT NULL,
          support_score DECIMAL(6,5) NULL,
          reviewed_by VARCHAR(64) NULL,
          reviewed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_claim_support (tenant_id, assertion_id, fact_revision_id, knowledge_source_id, support_type),
          KEY idx_airank_claim_support_assertion (tenant_id, project_id, assertion_id),
          CONSTRAINT fk_airank_claim_support_assertion FOREIGN KEY (assertion_id) REFERENCES airank_claim_assertions (id),
          CONSTRAINT fk_airank_claim_support_revision FOREIGN KEY (fact_revision_id) REFERENCES airank_fact_revisions (id),
          CONSTRAINT fk_airank_claim_support_source FOREIGN KEY (knowledge_source_id) REFERENCES airank_knowledge_sources (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute("ALTER TABLE airank_fact_atoms ADD COLUMN current_revision_id VARCHAR(64) NULL AFTER fact_text")
    op.execute("ALTER TABLE airank_fact_atoms ADD COLUMN risk_level VARCHAR(32) NOT NULL DEFAULT 'medium' AFTER current_revision_id")
    op.execute("ALTER TABLE airank_fact_atoms ADD COLUMN valid_until DATETIME(3) NULL AFTER risk_level")
    op.execute("CREATE INDEX idx_airank_fact_expiry ON airank_fact_atoms (tenant_id, project_id, status, valid_until)")


def downgrade() -> None:
    # Governed evidence is append-only. Export and migrate explicitly instead of
    # silently dropping revisions, conflicts, assertions, or claim supports.
    pass
