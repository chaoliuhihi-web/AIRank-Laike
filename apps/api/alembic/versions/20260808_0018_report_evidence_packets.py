"""add immutable customer report evidence packets

Revision ID: 20260808_0018
Revises: 20260808_0017
Create Date: 2026-08-08 14:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0018"
down_revision = "20260808_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_report_evidence_packets (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          report_id VARCHAR(64) NOT NULL,
          schema_version VARCHAR(64) NOT NULL,
          report_sha256 CHAR(64) NOT NULL,
          source_record_sha256 CHAR(64) NOT NULL,
          object_ref_id VARCHAR(64) NOT NULL,
          content_sha256 CHAR(64) NOT NULL,
          byte_size BIGINT NOT NULL,
          summary_json JSON NOT NULL,
          idempotency_key VARCHAR(160) NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_report_packet_version
            (tenant_id, report_id, schema_version),
          UNIQUE KEY uk_airank_report_packet_idempotency
            (tenant_id, idempotency_key),
          UNIQUE KEY uk_airank_report_packet_content
            (tenant_id, content_sha256),
          KEY idx_airank_report_packet_project
            (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_report_packet_report
            FOREIGN KEY (report_id) REFERENCES airank_reports (id),
          CONSTRAINT fk_airank_report_packet_object
            FOREIGN KEY (object_ref_id) REFERENCES airank_object_refs (id),
          CONSTRAINT fk_airank_report_packet_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Customer evidence packets are immutable delivery records. Destructive
    # rollback requires an explicit export and migration plan.
    pass
