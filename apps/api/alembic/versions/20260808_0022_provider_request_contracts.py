"""persist public provider request contracts for historical audit joins

Revision ID: 20260808_0022
Revises: 20260808_0021
Create Date: 2026-08-08 19:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260808_0022"
down_revision = "20260808_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE airank_provider_manifests
          ADD COLUMN request_defaults_json JSON NULL AFTER lifecycle_json
        """
    )
    op.execute(
        """
        ALTER TABLE airank_provider_routes
          ADD COLUMN request_contract_json JSON NULL AFTER model_name
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE airank_provider_routes
          DROP COLUMN request_contract_json
        """
    )
    op.execute(
        """
        ALTER TABLE airank_provider_manifests
          DROP COLUMN request_defaults_json
        """
    )
