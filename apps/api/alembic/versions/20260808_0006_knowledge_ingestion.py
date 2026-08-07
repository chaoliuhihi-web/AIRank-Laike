"""add immutable knowledge source content and exact-boundary segments

Revision ID: 20260808_0006
Revises: 20260808_0005
Create Date: 2026-08-08 15:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0006"
down_revision = "20260808_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE airank_knowledge_sources MODIFY source_uri VARCHAR(2048) NULL")
    op.execute(
        "ALTER TABLE airank_knowledge_sources "
        "ADD COLUMN idempotency_key VARCHAR(160) NULL AFTER parent_source_id"
    )
    op.execute(
        "ALTER TABLE airank_knowledge_sources "
        "ADD UNIQUE KEY uk_airank_knowledge_source_idempotency "
        "(tenant_id, project_id, idempotency_key)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_knowledge_source_contents (
          knowledge_source_id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          content_text MEDIUMTEXT NOT NULL,
          content_sha256 CHAR(64) NOT NULL,
          content_type VARCHAR(128) NOT NULL DEFAULT 'text/plain',
          byte_size BIGINT NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (knowledge_source_id),
          UNIQUE KEY uk_airank_knowledge_content_hash (tenant_id, project_id, content_sha256),
          CONSTRAINT fk_airank_knowledge_content_source FOREIGN KEY (knowledge_source_id) REFERENCES airank_knowledge_sources (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_knowledge_segments (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          knowledge_source_id VARCHAR(64) NOT NULL,
          segment_index INT NOT NULL,
          segment_text TEXT NOT NULL,
          source_start INT NOT NULL,
          source_end INT NOT NULL,
          content_sha256 CHAR(64) NOT NULL,
          embedding_status VARCHAR(32) NOT NULL DEFAULT 'pending',
          embedding_model VARCHAR(160) NULL,
          embedding_ref VARCHAR(255) NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_knowledge_segment_index (tenant_id, knowledge_source_id, segment_index),
          KEY idx_airank_knowledge_segment_hash (tenant_id, project_id, content_sha256),
          KEY idx_airank_knowledge_segment_embedding (tenant_id, project_id, embedding_status),
          CONSTRAINT fk_airank_knowledge_segment_source FOREIGN KEY (knowledge_source_id) REFERENCES airank_knowledge_sources (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        "ALTER TABLE airank_fact_atoms "
        "ADD CONSTRAINT fk_airank_fact_current_revision "
        "FOREIGN KEY (current_revision_id) REFERENCES airank_fact_revisions (id)"
    )


def downgrade() -> None:
    # Immutable source snapshots and exact citation boundaries are evidence.
    # Destructive downgrade requires an explicit export/migration.
    pass
