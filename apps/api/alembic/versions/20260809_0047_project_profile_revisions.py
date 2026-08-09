"""add immutable project profile revisions

Revision ID: 20260809_0047
Revises: 20260809_0046
Create Date: 2026-08-09 23:10:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0047"
down_revision = "20260809_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_project_profile_revisions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          revision_number INT NOT NULL,
          brand_name VARCHAR(120) NOT NULL,
          company_name VARCHAR(160) NOT NULL,
          website_url VARCHAR(2048) NOT NULL,
          industry VARCHAR(120) NOT NULL,
          region VARCHAR(128) NULL,
          products_services_json JSON NOT NULL,
          selling_points_json JSON NOT NULL,
          target_audience_json JSON NOT NULL,
          change_note VARCHAR(500) NOT NULL,
          changed_by VARCHAR(128) NOT NULL,
          previous_profile_sha256 CHAR(64) NOT NULL,
          profile_sha256 CHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_project_profile_revision (tenant_id, project_id, revision_number),
          KEY idx_airank_project_profile_hash (tenant_id, project_id, profile_sha256),
          KEY idx_airank_project_profile_changed (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_project_profile_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Project profile revisions are audit evidence. Destructive rollback requires
    # an explicit retention/export decision.
    pass
