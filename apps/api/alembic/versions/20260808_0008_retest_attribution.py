"""add evidence-backed retest comparison and report fields

Revision ID: 20260808_0008
Revises: 20260808_0007
Create Date: 2026-08-08 17:00:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0008"
down_revision = "20260808_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE airank_retest_runs ADD COLUMN package_id VARCHAR(64) NULL AFTER project_id")
    op.execute("ALTER TABLE airank_retest_runs ADD COLUMN observation_window_id VARCHAR(64) NULL AFTER package_id")
    op.execute("ALTER TABLE airank_retest_runs ADD COLUMN comparison_contract_version VARCHAR(64) NULL AFTER compare_run_id")
    op.execute("ALTER TABLE airank_retest_runs ADD COLUMN created_by VARCHAR(64) NULL AFTER comparison_contract_version")
    op.execute("ALTER TABLE airank_retest_runs ADD UNIQUE KEY uk_airank_retest_window (tenant_id, observation_window_id)")
    op.execute("ALTER TABLE airank_retest_runs ADD CONSTRAINT fk_airank_retest_package FOREIGN KEY (package_id) REFERENCES airank_publish_packages (id)")
    op.execute("ALTER TABLE airank_retest_runs ADD CONSTRAINT fk_airank_retest_window FOREIGN KEY (observation_window_id) REFERENCES airank_retest_observation_windows (id)")
    op.execute("ALTER TABLE airank_reports ADD COLUMN report_sha256 CHAR(64) NULL AFTER metrics_json")
    op.execute("ALTER TABLE airank_reports ADD COLUMN evidence_index_json JSON NULL AFTER report_sha256")
    op.execute("CREATE INDEX idx_airank_reports_hash ON airank_reports (tenant_id, project_id, report_sha256)")
    op.execute("ALTER TABLE airank_reports ADD UNIQUE KEY uk_airank_report_retest_type (tenant_id, retest_run_id, report_type)")


def downgrade() -> None:
    # Retest results and reports are delivery evidence. Destructive rollback is
    # intentionally disabled and requires an explicit export/migration.
    pass
