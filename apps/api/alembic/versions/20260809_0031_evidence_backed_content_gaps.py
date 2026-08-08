"""add evidence-backed content-gap derivation runs

Revision ID: 20260809_0031
Revises: 20260809_0030
Create Date: 2026-08-09 05:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0031"
down_revision = "20260809_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN contract_version VARCHAR(64) NULL AFTER gap_type"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN derivation_policy VARCHAR(96) NULL AFTER contract_version"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN answer_snapshot_ids JSON NULL AFTER related_competitor_ids"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN evidence_snapshot_ids JSON NULL AFTER answer_snapshot_ids"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN citation_ids JSON NULL AFTER evidence_snapshot_ids"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN fact_atom_ids JSON NULL AFTER citation_ids"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN evidence_summary_json JSON NULL AFTER suggested_asset_type"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN evidence_sha256 CHAR(64) NULL AFTER evidence_summary_json"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN quality_report_sha256 CHAR(64) NULL AFTER evidence_sha256"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD COLUMN derived_by VARCHAR(128) NULL AFTER quality_report_sha256"
    )
    op.execute(
        "ALTER TABLE airank_content_gaps "
        "ADD UNIQUE KEY uk_airank_content_gap_evidence "
        "(tenant_id, project_id, run_id, gap_type, evidence_sha256)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_content_gap_derivation_runs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          scan_run_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          derivation_policy VARCHAR(96) NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          quality_report_sha256 CHAR(64) NOT NULL,
          evidence_basis_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'succeeded',
          gap_ids_json JSON NOT NULL,
          gap_count INT NOT NULL,
          skipped_group_count INT NOT NULL DEFAULT 0,
          created_by VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_gap_derivation_idempotency
            (tenant_id, project_id, idempotency_key),
          UNIQUE KEY uk_airank_gap_derivation_run
            (tenant_id, project_id, scan_run_id, contract_version),
          KEY idx_airank_gap_derivation_project
            (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_gap_derivation_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_gap_derivation_scan_run
            FOREIGN KEY (scan_run_id) REFERENCES airank_scan_runs (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Gap provenance is customer-facing decision evidence. A deliberate rollback
    # must export and reconcile it instead of silently dropping the audit chain.
    pass
