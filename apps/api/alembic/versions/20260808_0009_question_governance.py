"""add governed buyer-question maps and immutable revisions

Revision ID: 20260808_0009
Revises: 20260808_0008
Create Date: 2026-08-08 17:00:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260808_0009"
down_revision = "20260808_0008"
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
        CREATE TABLE IF NOT EXISTS airank_question_maps (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          map_version_id VARCHAR(64) NOT NULL,
          taxonomy_version VARCHAR(64) NOT NULL,
          input_sha256 CHAR(64) NOT NULL,
          input_json JSON NOT NULL,
          output_manifest_json JSON NOT NULL,
          question_count INT NOT NULL,
          duplicate_count INT NOT NULL DEFAULT 0,
          status VARCHAR(32) NOT NULL DEFAULT 'compiled',
          created_by VARCHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_question_map_version (tenant_id, project_id, map_version_id),
          KEY idx_airank_question_maps_project (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_question_maps_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    if not _has_column("airank_buyer_questions", "question_map_id"):
        op.execute("ALTER TABLE airank_buyer_questions ADD COLUMN question_map_id VARCHAR(64) NULL AFTER project_id")
    if not _has_column("airank_buyer_questions", "current_revision_id"):
        op.execute("ALTER TABLE airank_buyer_questions ADD COLUMN current_revision_id VARCHAR(64) NULL AFTER question_map_id")
    if not _has_column("airank_buyer_questions", "taxonomy_version"):
        op.execute("ALTER TABLE airank_buyer_questions ADD COLUMN taxonomy_version VARCHAR(64) NULL AFTER current_revision_id")
    if not _has_column("airank_buyer_questions", "dedupe_sha256"):
        op.execute("ALTER TABLE airank_buyer_questions ADD COLUMN dedupe_sha256 CHAR(64) NULL AFTER taxonomy_version")
    if not _has_index("airank_buyer_questions", "idx_airank_questions_dedupe"):
        op.execute("CREATE INDEX idx_airank_questions_dedupe ON airank_buyer_questions (tenant_id, project_id, dedupe_sha256)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_buyer_question_revisions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          question_id VARCHAR(64) NOT NULL,
          question_map_id VARCHAR(64) NULL,
          revision_number INT NOT NULL,
          question_version_id VARCHAR(64) NOT NULL,
          taxonomy_version VARCHAR(64) NOT NULL,
          question_text TEXT NOT NULL,
          dedupe_sha256 CHAR(64) NOT NULL,
          question_type VARCHAR(64) NOT NULL,
          intent VARCHAR(64) NOT NULL,
          funnel_stage VARCHAR(64) NOT NULL,
          prompt_style VARCHAR(32) NOT NULL,
          temporal_scope VARCHAR(32) NOT NULL,
          scenario VARCHAR(64) NOT NULL,
          region VARCHAR(128) NULL,
          cohort_type VARCHAR(32) NOT NULL,
          source_kind VARCHAR(64) NOT NULL,
          source_ref VARCHAR(255) NOT NULL,
          evidence_level VARCHAR(64) NOT NULL,
          observed_query TINYINT(1) NOT NULL DEFAULT 0,
          provenance_json JSON NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'suggested',
          created_by VARCHAR(64) NOT NULL,
          reviewed_by VARCHAR(64) NULL,
          reviewed_at DATETIME(3) NULL,
          review_note VARCHAR(1000) NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_question_revision_number (tenant_id, question_id, revision_number),
          UNIQUE KEY uk_airank_question_revision_version (tenant_id, question_id, question_version_id),
          KEY idx_airank_question_revision_project (tenant_id, project_id, status, created_at),
          KEY idx_airank_question_revision_dedupe (tenant_id, project_id, dedupe_sha256),
          CONSTRAINT fk_airank_question_revision_question FOREIGN KEY (question_id) REFERENCES airank_buyer_questions (id),
          CONSTRAINT fk_airank_question_revision_map FOREIGN KEY (question_map_id) REFERENCES airank_question_maps (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_buyer_question_reviews (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          question_id VARCHAR(64) NOT NULL,
          question_revision_id VARCHAR(64) NOT NULL,
          previous_status VARCHAR(32) NOT NULL,
          action VARCHAR(32) NOT NULL,
          review_note VARCHAR(1000) NOT NULL,
          reviewed_by VARCHAR(64) NOT NULL,
          reviewed_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          KEY idx_airank_question_reviews_question (tenant_id, question_id, reviewed_at),
          CONSTRAINT fk_airank_question_review_question FOREIGN KEY (question_id) REFERENCES airank_buyer_questions (id),
          CONSTRAINT fk_airank_question_review_revision FOREIGN KEY (question_revision_id) REFERENCES airank_buyer_question_revisions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        UPDATE airank_buyer_questions
        SET taxonomy_version='legacy_unclassified',
            dedupe_sha256=SHA2(LOWER(TRIM(question_text)), 256)
        WHERE taxonomy_version IS NULL OR dedupe_sha256 IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO airank_buyer_question_revisions (
          id, tenant_id, project_id, question_id, question_map_id, revision_number,
          question_version_id, taxonomy_version, question_text, dedupe_sha256,
          question_type, intent, funnel_stage, prompt_style, temporal_scope,
          scenario, region, cohort_type, source_kind, source_ref, evidence_level,
          observed_query, provenance_json, status, created_by, created_at
        )
        SELECT
          CONCAT('qrev_', LEFT(SHA2(CONCAT(tenant_id, '|', id, '|legacy'), 256), 20)),
          tenant_id, project_id, id, NULL, 1,
          CONCAT('question_v_', LEFT(SHA2(CONCAT(question_text, '|legacy'), 256), 20)),
          'legacy_unclassified', question_text, dedupe_sha256,
          question_type, intent, funnel_stage, 'exploratory', 'evergreen',
          'generic', NULL, 'unclassified', source, 'legacy-row', 'imported',
          0, COALESCE(metadata_json, JSON_OBJECT()), status, 'migration', created_at
        FROM airank_buyer_questions
        WHERE current_revision_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE airank_buyer_questions q
        JOIN airank_buyer_question_revisions r
          ON r.tenant_id=q.tenant_id AND r.question_id=q.id AND r.revision_number=1
        SET q.current_revision_id=r.id
        WHERE q.current_revision_id IS NULL
        """
    )
    if not _has_foreign_key("airank_buyer_questions", "fk_airank_question_current_revision"):
        op.execute(
            "ALTER TABLE airank_buyer_questions "
            "ADD CONSTRAINT fk_airank_question_current_revision "
            "FOREIGN KEY (current_revision_id) REFERENCES airank_buyer_question_revisions (id)"
        )
    if not _has_foreign_key("airank_buyer_questions", "fk_airank_question_map"):
        op.execute(
            "ALTER TABLE airank_buyer_questions "
            "ADD CONSTRAINT fk_airank_question_map "
            "FOREIGN KEY (question_map_id) REFERENCES airank_question_maps (id)"
        )


def downgrade() -> None:
    # Question maps and revisions are audit evidence. Destructive downgrade requires export/migration.
    pass
