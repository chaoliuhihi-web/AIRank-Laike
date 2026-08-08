"""add immutable citation source captures and exact source boundaries

Revision ID: 20260808_0014
Revises: 20260808_0013
Create Date: 2026-08-08 15:30:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260808_0014"
down_revision = "20260808_0013"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(column["name"] == column_name for column in sa.inspect(op.get_bind()).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _has_foreign_key(table_name: str, constraint_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        foreign_key.get("name") == constraint_name
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_citation_source_captures (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          citation_id VARCHAR(64) NOT NULL,
          job_id VARCHAR(64) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          requested_url VARCHAR(2048) NOT NULL,
          final_url VARCHAR(2048) NULL,
          status VARCHAR(32) NOT NULL COMMENT 'queued/running/completed/blocked/failed',
          capture_version VARCHAR(64) NOT NULL,
          evidence_grade VARCHAR(64) NULL,
          response_status INT NULL,
          content_type VARCHAR(255) NULL,
          response_bytes BIGINT NULL,
          content_sha256 CHAR(64) NULL,
          visible_text_sha256 CHAR(64) NULL,
          raw_object_ref_id VARCHAR(64) NULL,
          text_object_ref_id VARCHAR(64) NULL,
          connected_ip VARCHAR(64) NULL,
          redirect_count INT NULL,
          error_code VARCHAR(128) NULL,
          error_message TEXT NULL,
          requested_by VARCHAR(64) NOT NULL,
          started_at DATETIME(3) NULL,
          completed_at DATETIME(3) NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_citation_capture_idempotency
            (tenant_id, project_id, idempotency_key),
          UNIQUE KEY uk_airank_citation_capture_job (tenant_id, job_id),
          KEY idx_airank_citation_capture_citation
            (tenant_id, citation_id, created_at),
          KEY idx_airank_citation_capture_status (status, updated_at),
          CONSTRAINT fk_airank_citation_capture_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_citation_capture_citation
            FOREIGN KEY (citation_id) REFERENCES airank_source_citations (id),
          CONSTRAINT fk_airank_citation_capture_job
            FOREIGN KEY (job_id) REFERENCES airank_async_jobs (id),
          CONSTRAINT fk_airank_citation_capture_raw_object
            FOREIGN KEY (raw_object_ref_id) REFERENCES airank_object_refs (id),
          CONSTRAINT fk_airank_citation_capture_text_object
            FOREIGN KEY (text_object_ref_id) REFERENCES airank_object_refs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_citation_source_segments (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          capture_id VARCHAR(64) NOT NULL,
          segment_index INT NOT NULL,
          source_start INT NOT NULL,
          source_end INT NOT NULL,
          segment_text TEXT NOT NULL,
          segment_sha256 CHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_citation_segment_index
            (tenant_id, capture_id, segment_index),
          KEY idx_airank_citation_segment_project
            (tenant_id, project_id, capture_id),
          CONSTRAINT fk_airank_citation_segment_capture
            FOREIGN KEY (capture_id) REFERENCES airank_citation_source_captures (id),
          CONSTRAINT fk_airank_citation_segment_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    review_columns = (
        ("source_capture_id", "VARCHAR(64) NULL AFTER source_object_ref_id"),
        ("source_segment_id", "VARCHAR(64) NULL AFTER source_capture_id"),
        ("source_start", "INT NULL AFTER source_segment_id"),
        ("source_end", "INT NULL AFTER source_start"),
    )
    for column_name, definition in review_columns:
        if not _has_column("airank_citation_support_reviews", column_name):
            op.execute(
                f"ALTER TABLE airank_citation_support_reviews ADD COLUMN {column_name} {definition}"
            )
    if not _has_index("airank_citation_support_reviews", "idx_airank_citation_support_capture"):
        op.execute(
            "CREATE INDEX idx_airank_citation_support_capture "
            "ON airank_citation_support_reviews "
            "(tenant_id, source_capture_id, source_segment_id)"
        )
    if not _has_foreign_key(
        "airank_citation_support_reviews", "fk_airank_citation_support_capture"
    ):
        op.execute(
            "ALTER TABLE airank_citation_support_reviews "
            "ADD CONSTRAINT fk_airank_citation_support_capture "
            "FOREIGN KEY (source_capture_id) REFERENCES airank_citation_source_captures (id)"
        )
    if not _has_foreign_key(
        "airank_citation_support_reviews", "fk_airank_citation_support_segment"
    ):
        op.execute(
            "ALTER TABLE airank_citation_support_reviews "
            "ADD CONSTRAINT fk_airank_citation_support_segment "
            "FOREIGN KEY (source_segment_id) REFERENCES airank_citation_source_segments (id)"
        )


def downgrade() -> None:
    # Citation captures and exact review boundaries are customer evidence.
    # Destructive downgrade requires an explicit export and migration plan.
    pass
