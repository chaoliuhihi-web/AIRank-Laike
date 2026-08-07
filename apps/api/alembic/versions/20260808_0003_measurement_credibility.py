"""add evidence-grade measurement contracts

Revision ID: 20260808_0003
Revises: 20260517_0002
Create Date: 2026-08-08 12:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0003"
down_revision = "20260517_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_prompt_versions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          question_id VARCHAR(64) NOT NULL,
          cohort_type VARCHAR(32) NOT NULL,
          template_version VARCHAR(32) NOT NULL,
          prompt_text TEXT NOT NULL,
          prompt_sha256 CHAR(64) NOT NULL,
          metadata_json JSON NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (tenant_id, id),
          UNIQUE KEY uk_airank_prompt_version_hash (tenant_id, project_id, cohort_type, prompt_sha256, template_version),
          KEY idx_airank_prompt_versions_question (tenant_id, project_id, question_id, cohort_type),
          CONSTRAINT fk_airank_prompt_versions_project FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_prompt_versions_question FOREIGN KEY (question_id) REFERENCES airank_buyer_questions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute("ALTER TABLE airank_scan_runs ADD COLUMN cohort_type VARCHAR(32) NOT NULL DEFAULT 'blind' AFTER run_type")
    op.execute("ALTER TABLE airank_scan_runs ADD COLUMN repetitions INT NOT NULL DEFAULT 3 AFTER cohort_type")
    op.execute("ALTER TABLE airank_scan_runs ADD COLUMN collector_surfaces_json JSON NULL AFTER repetitions")

    op.execute("ALTER TABLE airank_scan_tasks DROP INDEX uk_airank_scan_tasks_once")
    op.execute("ALTER TABLE airank_scan_tasks ADD COLUMN cohort_type VARCHAR(32) NOT NULL DEFAULT 'blind' AFTER provider")
    op.execute("ALTER TABLE airank_scan_tasks ADD COLUMN prompt_version_id VARCHAR(64) NOT NULL DEFAULT 'prompt_v_legacy' AFTER cohort_type")
    op.execute("ALTER TABLE airank_scan_tasks ADD COLUMN sample_index INT NOT NULL DEFAULT 1 AFTER prompt_version_id")
    op.execute("ALTER TABLE airank_scan_tasks ADD COLUMN session_id VARCHAR(96) NOT NULL DEFAULT 'session_legacy' AFTER sample_index")
    op.execute("ALTER TABLE airank_scan_tasks ADD COLUMN collector_surface VARCHAR(32) NOT NULL DEFAULT 'web' AFTER session_id")
    op.execute("ALTER TABLE airank_scan_tasks ADD COLUMN evidence_level VARCHAR(64) NOT NULL DEFAULT 'consumer_web' AFTER collector_surface")
    op.execute(
        "ALTER TABLE airank_scan_tasks ADD UNIQUE KEY uk_airank_scan_tasks_sample "
        "(tenant_id, run_id, question_id, provider, cohort_type, collector_surface, sample_index)"
    )

    answer_columns = (
        "ADD COLUMN cohort_type VARCHAR(32) NOT NULL DEFAULT 'blind' AFTER provider",
        "ADD COLUMN prompt_version_id VARCHAR(64) NULL AFTER cohort_type",
        "ADD COLUMN sample_index INT NOT NULL DEFAULT 1 AFTER prompt_version_id",
        "ADD COLUMN session_id VARCHAR(96) NULL AFTER sample_index",
        "ADD COLUMN collector_surface VARCHAR(32) NOT NULL DEFAULT 'web' AFTER session_id",
        "ADD COLUMN evidence_level VARCHAR(64) NOT NULL DEFAULT 'consumer_web' AFTER collector_surface",
        "ADD COLUMN sample_status VARCHAR(32) NOT NULL DEFAULT 'valid' AFTER evidence_level",
        "ADD COLUMN mention_class VARCHAR(32) NOT NULL DEFAULT 'not_mentioned' AFTER brand_rank",
        "ADD COLUMN target_entity_mentions_json JSON NULL AFTER mention_class",
        "ADD COLUMN model_name VARCHAR(128) NULL AFTER target_entity_mentions_json",
        "ADD COLUMN model_version VARCHAR(128) NULL AFTER model_name",
        "ADD COLUMN search_enabled TINYINT(1) NULL AFTER model_version",
        "ADD COLUMN locale VARCHAR(32) NOT NULL DEFAULT 'zh-CN' AFTER search_enabled",
        "ADD COLUMN region VARCHAR(64) NULL AFTER locale",
        "ADD COLUMN answer_sha256 CHAR(64) NULL AFTER answer_text",
        "ADD COLUMN raw_response_sha256 CHAR(64) NULL AFTER answer_sha256",
        "ADD COLUMN screenshot_ref_id VARCHAR(64) NULL AFTER raw_response_ref_id",
        "ADD COLUMN source_panel_ref_id VARCHAR(64) NULL AFTER screenshot_ref_id",
        "ADD COLUMN request_metadata_ref_id VARCHAR(64) NULL AFTER source_panel_ref_id",
    )
    for column in answer_columns:
        op.execute(f"ALTER TABLE airank_answer_snapshots {column}")
    op.execute("CREATE INDEX idx_airank_snapshots_cohort ON airank_answer_snapshots (tenant_id, project_id, cohort_type, collector_surface, sample_status)")
    op.execute("CREATE INDEX idx_airank_snapshots_hash ON airank_answer_snapshots (tenant_id, answer_sha256)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_evidence_snapshots (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          answer_snapshot_id VARCHAR(64) NOT NULL,
          raw_response_json MEDIUMTEXT NOT NULL,
          raw_response_sha256 CHAR(64) NOT NULL,
          screenshot_ref_id VARCHAR(64) NULL,
          source_panel_ref_id VARCHAR(64) NULL,
          request_metadata_json JSON NULL,
          captured_at DATETIME(3) NOT NULL,
          created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_evidence_answer (tenant_id, answer_snapshot_id),
          KEY idx_airank_evidence_hash (tenant_id, raw_response_sha256),
          CONSTRAINT fk_airank_evidence_answer FOREIGN KEY (answer_snapshot_id) REFERENCES airank_answer_snapshots (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Evidence tables are append-only. A destructive downgrade could erase audit
    # records, so rollback is intentionally disabled and requires an export/migration.
    pass
