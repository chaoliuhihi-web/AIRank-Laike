"""add versioned provider pricing and immutable usage cost derivations

Revision ID: 20260809_0042
Revises: 20260809_0041
Create Date: 2026-08-09 11:20:00.000000
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260809_0042"
down_revision = "20260809_0041"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _has_index(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def upgrade() -> None:
    if not _has_column("airank_provider_usage_events", "cost_precision_status"):
        op.add_column(
            "airank_provider_usage_events",
            sa.Column(
                "cost_precision_status",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            ),
        )
    if not _has_column("airank_provider_usage_events", "cost_source"):
        op.add_column(
            "airank_provider_usage_events",
            sa.Column(
                "cost_source",
                sa.String(length=80),
                nullable=False,
                server_default="missing",
            ),
        )
    if not _has_column("airank_provider_usage_events", "raw_usage_sha256"):
        op.add_column(
            "airank_provider_usage_events",
            sa.Column("raw_usage_sha256", sa.String(length=64), nullable=True),
        )
    op.execute(
        """
        UPDATE airank_provider_usage_events
        SET raw_usage_sha256=SHA2(CONCAT_WS('|',
          'airank.provider-usage-legacy.v1', id, tenant_id, project_id,
          request_audit_id, provider_key, model_name,
          COALESCE(CAST(input_tokens AS CHAR), 'null'),
          COALESCE(CAST(output_tokens AS CHAR), 'null'),
          COALESCE(CAST(total_tokens AS CHAR), 'null'),
          precision_status, usage_source,
          COALESCE(CAST(cost_amount AS CHAR), 'null'),
          COALESCE(cost_currency, 'null'), occurred_at
        ), 256)
        WHERE raw_usage_sha256 IS NULL
        """
    )
    op.alter_column(
        "airank_provider_usage_events",
        "raw_usage_sha256",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    if not _has_index("airank_provider_usage_events", "idx_airank_provider_usage_precision"):
        op.create_index(
            "idx_airank_provider_usage_precision",
            "airank_provider_usage_events",
            ["tenant_id", "precision_status", "cost_precision_status", "occurred_at"],
            unique=False,
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_price_versions (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          provider_key VARCHAR(64) NOT NULL,
          route_id VARCHAR(64) NOT NULL,
          model_name VARCHAR(160) NOT NULL,
          catalog_version INT NOT NULL,
          currency CHAR(3) NOT NULL,
          pricing_unit VARCHAR(32) NOT NULL,
          input_price_per_million DECIMAL(20,8) NOT NULL,
          output_price_per_million DECIMAL(20,8) NOT NULL,
          effective_from DATETIME(3) NOT NULL,
          effective_until DATETIME(3) NULL,
          source_kind VARCHAR(48) NOT NULL,
          source_reference VARCHAR(2048) NOT NULL,
          source_sha256 CHAR(64) NOT NULL,
          reason VARCHAR(500) NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_price_version
            (tenant_id, provider_key, route_id, model_name, catalog_version),
          UNIQUE KEY uk_airank_provider_price_source
            (tenant_id, source_sha256),
          KEY idx_airank_provider_price_effective
            (tenant_id, provider_key, model_name, route_id, effective_from)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_provider_usage_costs (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          usage_event_id VARCHAR(64) NOT NULL,
          price_version_id VARCHAR(64) NOT NULL,
          input_cost_amount DECIMAL(20,12) NOT NULL,
          output_cost_amount DECIMAL(20,12) NOT NULL,
          total_cost_amount DECIMAL(20,12) NOT NULL,
          cost_currency CHAR(3) NOT NULL,
          precision_status VARCHAR(32) NOT NULL,
          cost_source VARCHAR(80) NOT NULL,
          calculation_contract_json JSON NOT NULL,
          calculation_sha256 CHAR(64) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_provider_usage_cost_calculation
            (usage_event_id, calculation_sha256),
          KEY idx_airank_provider_usage_cost_tenant
            (tenant_id, precision_status, created_at),
          KEY idx_airank_provider_usage_cost_price (price_version_id),
          CONSTRAINT fk_airank_provider_usage_cost_event
            FOREIGN KEY (usage_event_id) REFERENCES airank_provider_usage_events (id),
          CONSTRAINT fk_airank_provider_usage_cost_price
            FOREIGN KEY (price_version_id) REFERENCES airank_provider_price_versions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def downgrade() -> None:
    # Usage, price provenance, and cost calculations are financial audit evidence.
    # Destructive rollback requires an explicit export and retention decision.
    pass
