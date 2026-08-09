"""add governed brand graph and immutable measurement snapshots

Revision ID: 20260809_0039
Revises: 20260809_0038
Create Date: 2026-08-09 21:30:00.000000
"""

from __future__ import annotations

from alembic import op


revision = "20260809_0039"
down_revision = "20260809_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_brand_entities (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          entity_role VARCHAR(32) NOT NULL COMMENT 'target/competitor/related',
          entity_kind VARCHAR(32) NOT NULL COMMENT 'brand/company/product/service',
          canonical_name VARCHAR(255) NOT NULL,
          normalized_name VARCHAR(255) NOT NULL,
          website_url VARCHAR(2048) NULL,
          external_ref_type VARCHAR(64) NULL,
          external_ref_id VARCHAR(128) NULL,
          usage_scope VARCHAR(32) NOT NULL COMMENT 'measurement_only/public_and_measurement',
          fact_revision_id VARCHAR(64) NOT NULL,
          evidence_manifest_json JSON NOT NULL,
          evidence_manifest_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_brand_entity_name
            (tenant_id, project_id, entity_role, entity_kind, normalized_name),
          KEY idx_airank_brand_entity_project
            (tenant_id, project_id, status, entity_role, entity_kind),
          CONSTRAINT fk_airank_brand_entity_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_brand_entity_fact_revision
            FOREIGN KEY (fact_revision_id) REFERENCES airank_fact_revisions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_brand_entity_aliases (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          entity_id VARCHAR(64) NOT NULL,
          alias_text VARCHAR(255) NOT NULL,
          normalized_alias VARCHAR(255) NOT NULL,
          alias_type VARCHAR(32) NOT NULL
            COMMENT 'official/english/abbreviation/former_name/misspelling/product_variant',
          language_code VARCHAR(16) NULL,
          usage_scope VARCHAR(32) NOT NULL COMMENT 'measurement_only/public_and_measurement',
          fact_revision_id VARCHAR(64) NOT NULL,
          evidence_manifest_json JSON NOT NULL,
          evidence_manifest_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_brand_alias_entity
            (tenant_id, project_id, entity_id, normalized_alias),
          KEY idx_airank_brand_alias_normalized
            (tenant_id, project_id, normalized_alias, status),
          CONSTRAINT fk_airank_brand_alias_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_brand_alias_entity
            FOREIGN KEY (entity_id) REFERENCES airank_brand_entities (id),
          CONSTRAINT fk_airank_brand_alias_fact_revision
            FOREIGN KEY (fact_revision_id) REFERENCES airank_fact_revisions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_brand_relations (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          subject_entity_id VARCHAR(64) NOT NULL,
          predicate VARCHAR(64) NOT NULL
            COMMENT 'legal_name_of/owns_product/offers/competitor_of/former_name_of/part_of',
          object_entity_id VARCHAR(64) NOT NULL,
          usage_scope VARCHAR(32) NOT NULL COMMENT 'measurement_only/public_and_measurement',
          fact_revision_id VARCHAR(64) NOT NULL,
          evidence_manifest_json JSON NOT NULL,
          evidence_manifest_sha256 CHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'active/disabled',
          request_sha256 CHAR(64) NOT NULL,
          version INT NOT NULL DEFAULT 1,
          created_by VARCHAR(128) NOT NULL,
          updated_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          updated_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_brand_relation
            (tenant_id, project_id, subject_entity_id, predicate, object_entity_id),
          KEY idx_airank_brand_relation_project
            (tenant_id, project_id, status, predicate),
          CONSTRAINT fk_airank_brand_relation_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id),
          CONSTRAINT fk_airank_brand_relation_subject
            FOREIGN KEY (subject_entity_id) REFERENCES airank_brand_entities (id),
          CONSTRAINT fk_airank_brand_relation_object
            FOREIGN KEY (object_entity_id) REFERENCES airank_brand_entities (id),
          CONSTRAINT fk_airank_brand_relation_fact_revision
            FOREIGN KEY (fact_revision_id) REFERENCES airank_fact_revisions (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_brand_graph_events (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          aggregate_type VARCHAR(32) NOT NULL COMMENT 'entity/alias/relation',
          aggregate_id VARCHAR(64) NOT NULL,
          event_type VARCHAR(64) NOT NULL,
          aggregate_version INT NOT NULL,
          request_sha256 CHAR(64) NOT NULL,
          previous_event_sha256 CHAR(64) NULL,
          event_sha256 CHAR(64) NOT NULL,
          actor_user_id VARCHAR(128) NOT NULL,
          trace_id VARCHAR(128) NOT NULL,
          payload_json JSON NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_brand_graph_event_version
            (tenant_id, aggregate_type, aggregate_id, aggregate_version),
          KEY idx_airank_brand_graph_event_project
            (tenant_id, project_id, aggregate_type, aggregate_id, created_at),
          CONSTRAINT fk_airank_brand_graph_event_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS airank_brand_graph_snapshots (
          id VARCHAR(64) NOT NULL,
          tenant_id VARCHAR(64) NOT NULL,
          project_id VARCHAR(64) NOT NULL,
          contract_version VARCHAR(64) NOT NULL,
          compiler_version VARCHAR(64) NOT NULL,
          status VARCHAR(32) NOT NULL COMMENT 'governed/partial/blocked/legacy_unverified',
          source_manifest_json JSON NOT NULL,
          source_manifest_sha256 CHAR(64) NOT NULL,
          graph_json JSON NOT NULL,
          graph_sha256 CHAR(64) NOT NULL,
          measurement_lexicon_json JSON NOT NULL,
          public_jsonld_json JSON NOT NULL,
          ambiguous_aliases_json JSON NOT NULL,
          known_limitations_json JSON NOT NULL,
          created_by VARCHAR(128) NOT NULL,
          created_at DATETIME(3) NOT NULL,
          PRIMARY KEY (id),
          UNIQUE KEY uk_airank_brand_graph_snapshot
            (tenant_id, project_id, graph_sha256),
          KEY idx_airank_brand_graph_snapshot_project
            (tenant_id, project_id, created_at),
          CONSTRAINT fk_airank_brand_graph_snapshot_project
            FOREIGN KEY (project_id) REFERENCES airank_projects (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )
    op.execute(
        "ALTER TABLE airank_scan_runs ADD COLUMN entity_graph_snapshot_id VARCHAR(64) NULL AFTER collector_surfaces_json"
    )
    op.execute(
        "ALTER TABLE airank_scan_runs ADD COLUMN entity_graph_sha256 CHAR(64) NULL AFTER entity_graph_snapshot_id"
    )
    op.execute(
        "ALTER TABLE airank_scan_runs ADD COLUMN entity_graph_status VARCHAR(32) NULL AFTER entity_graph_sha256"
    )
    op.execute(
        "ALTER TABLE airank_scan_runs ADD COLUMN entity_graph_limitations_json JSON NULL AFTER entity_graph_status"
    )
    op.execute(
        "ALTER TABLE airank_scan_runs ADD CONSTRAINT fk_airank_scan_run_entity_graph_snapshot FOREIGN KEY (entity_graph_snapshot_id) REFERENCES airank_brand_graph_snapshots (id)"
    )
    op.execute(
        "CREATE INDEX idx_airank_scan_run_entity_graph ON airank_scan_runs (tenant_id, project_id, entity_graph_snapshot_id)"
    )


def downgrade() -> None:
    # Entity evidence, graph events, and scan-bound snapshots are audit records.
    # Export and reconcile them before any deliberate rollback.
    pass
