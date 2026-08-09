from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import text

from apps.api import brand_graph_routes, main as api_main
from apps.api.brand_graph_routes import (
    BrandAliasWriteRequest,
    BrandEntityWriteRequest,
    MySQLBrandGraphRepository,
    normalize_entity_name,
)
from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def validate(name: str, payload: dict) -> None:
    contract = schema(name)
    Draft202012Validator.check_schema(contract)
    Draft202012Validator(contract, format_checker=FormatChecker()).validate(payload)


def create_repository() -> MySQLBrandGraphRepository:
    repository = MySQLBrandGraphRepository("sqlite+pysqlite:///:memory:")
    statements = [
        """
        CREATE TABLE airank_projects (
          id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, brand_name TEXT, name TEXT,
          website_url TEXT, industry TEXT, products_services_json TEXT,
          updated_at DATETIME, deleted_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_competitors (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, name TEXT,
          website_url TEXT, metadata_json TEXT, updated_at DATETIME, deleted_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_fact_atoms (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, current_revision_id TEXT,
          status TEXT, disclosure TEXT, risk_level TEXT, valid_until DATETIME, deleted_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_fact_revisions (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, fact_atom_id TEXT,
          revision_number INTEGER, content_sha256 TEXT, status TEXT, source_ids_json TEXT,
          valid_from DATETIME, valid_until DATETIME
        )
        """,
        """
        CREATE TABLE airank_fact_conflicts (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, fact_atom_id TEXT, status TEXT
        )
        """,
        """
        CREATE TABLE airank_knowledge_sources (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, content_sha256 TEXT,
          source_uri TEXT, authority_level TEXT, risk_level TEXT, status TEXT,
          valid_from DATETIME, valid_until DATETIME
        )
        """,
        """
        CREATE TABLE airank_brand_entities (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, entity_role TEXT,
          entity_kind TEXT, canonical_name TEXT, normalized_name TEXT, website_url TEXT,
          external_ref_type TEXT, external_ref_id TEXT, usage_scope TEXT,
          fact_revision_id TEXT, evidence_manifest_json TEXT,
          evidence_manifest_sha256 TEXT, status TEXT, request_sha256 TEXT,
          version INTEGER, created_by TEXT, updated_by TEXT,
          created_at DATETIME, updated_at DATETIME,
          UNIQUE (tenant_id, project_id, entity_role, entity_kind, normalized_name)
        )
        """,
        """
        CREATE TABLE airank_brand_entity_aliases (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, entity_id TEXT,
          alias_text TEXT, normalized_alias TEXT, alias_type TEXT, language_code TEXT,
          usage_scope TEXT, fact_revision_id TEXT, evidence_manifest_json TEXT,
          evidence_manifest_sha256 TEXT, status TEXT, request_sha256 TEXT,
          version INTEGER, created_by TEXT, updated_by TEXT,
          created_at DATETIME, updated_at DATETIME,
          UNIQUE (tenant_id, project_id, entity_id, normalized_alias)
        )
        """,
        """
        CREATE TABLE airank_brand_relations (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT,
          subject_entity_id TEXT, predicate TEXT, object_entity_id TEXT,
          usage_scope TEXT, fact_revision_id TEXT, evidence_manifest_json TEXT,
          evidence_manifest_sha256 TEXT, status TEXT, request_sha256 TEXT,
          version INTEGER, created_by TEXT, updated_by TEXT,
          created_at DATETIME, updated_at DATETIME,
          UNIQUE (tenant_id, project_id, subject_entity_id, predicate, object_entity_id)
        )
        """,
        """
        CREATE TABLE airank_brand_graph_events (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, aggregate_type TEXT,
          aggregate_id TEXT, event_type TEXT, aggregate_version INTEGER,
          request_sha256 TEXT, previous_event_sha256 TEXT, event_sha256 TEXT,
          actor_user_id TEXT, trace_id TEXT, payload_json TEXT, created_at DATETIME,
          UNIQUE (tenant_id, aggregate_type, aggregate_id, aggregate_version)
        )
        """,
        """
        CREATE TABLE airank_brand_graph_snapshots (
          id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, contract_version TEXT,
          compiler_version TEXT, status TEXT, source_manifest_json TEXT,
          source_manifest_sha256 TEXT, graph_json TEXT, graph_sha256 TEXT,
          measurement_lexicon_json TEXT, public_jsonld_json TEXT,
          ambiguous_aliases_json TEXT, known_limitations_json TEXT,
          created_by TEXT, created_at DATETIME,
          UNIQUE (tenant_id, project_id, graph_sha256)
        )
        """,
    ]
    with repository._engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(text("""
            INSERT INTO airank_projects (
              id, tenant_id, brand_name, name, website_url, industry,
              products_services_json, updated_at
            ) VALUES (
              'project_graph', 'tenant_graph', 'AIRank', '星河科技',
              'https://airank.example', 'GEO', '[\"来客\"]', '2026-08-09 09:00:00'
            )
        """))
        conn.execute(text("""
            INSERT INTO airank_knowledge_sources (
              id, tenant_id, project_id, content_sha256, source_uri,
              authority_level, risk_level, status
            ) VALUES
              ('source_target', 'tenant_graph', 'project_graph', :source_target_sha, 'https://airank.example/about', 'official', 'low', 'active'),
              ('source_competitor', 'tenant_graph', 'project_graph', :source_competitor_sha, 'https://competitor.example/about', 'official', 'low', 'active')
        """), {"source_target_sha": "1" * 64, "source_competitor_sha": "2" * 64})
        conn.execute(text("""
            INSERT INTO airank_fact_atoms (
              id, tenant_id, project_id, current_revision_id, status,
              disclosure, risk_level
            ) VALUES
              ('fact_target', 'tenant_graph', 'project_graph', 'revision_target', 'confirmed', 'public', 'low'),
              ('fact_competitor', 'tenant_graph', 'project_graph', 'revision_competitor', 'confirmed', 'public', 'low')
        """))
        conn.execute(text("""
            INSERT INTO airank_fact_revisions (
              id, tenant_id, project_id, fact_atom_id, revision_number,
              content_sha256, status, source_ids_json
            ) VALUES
              ('revision_target', 'tenant_graph', 'project_graph', 'fact_target', 1, :target_sha, 'approved', '[\"source_target\"]'),
              ('revision_competitor', 'tenant_graph', 'project_graph', 'fact_competitor', 1, :competitor_sha, 'approved', '[\"source_competitor\"]')
        """), {"target_sha": "a" * 64, "competitor_sha": "b" * 64})
    return repository


def entity_payload(*, role: str, name: str, revision_id: str) -> BrandEntityWriteRequest:
    return BrandEntityWriteRequest(
        entity_role=role,
        entity_kind="brand",
        canonical_name=name,
        website_url=f"https://{normalize_entity_name(name)}.example",
        usage_scope="public_and_measurement",
        fact_revision_id=revision_id,
    )


def test_entity_name_normalization_is_nfkc_case_and_space_insensitive() -> None:
    assert normalize_entity_name(" ＡＩ Rank ") == "airank"
    assert normalize_entity_name("星 河-科技") == "星河科技"


def test_graph_compiler_excludes_ambiguous_aliases_and_keeps_evidence() -> None:
    repository = create_repository()
    target = repository.create_entity(
        "tenant_graph", "project_graph",
        entity_payload(role="target", name="AIRank", revision_id="revision_target"),
        "reviewer_1", "trc_entity_target",
    )
    competitor = repository.create_entity(
        "tenant_graph", "project_graph",
        entity_payload(role="competitor", name="竞品科技", revision_id="revision_competitor"),
        "reviewer_1", "trc_entity_competitor",
    )
    for entity_id, revision_id in (
        (target.entity_id, "revision_target"),
        (competitor.entity_id, "revision_competitor"),
    ):
        repository.create_alias(
            "tenant_graph", "project_graph", entity_id,
            BrandAliasWriteRequest(
                alias_text="星河",
                alias_type="abbreviation",
                usage_scope="public_and_measurement",
                fact_revision_id=revision_id,
            ),
            "reviewer_1", f"trc_alias_{entity_id}",
        )

    snapshot = repository.compile_snapshot("tenant_graph", "project_graph", "reviewer_1")

    assert snapshot.status == "partial"
    assert snapshot.ambiguous_aliases[0]["observed_values"] == ["星河"]
    assert snapshot.measurement_lexicon["target"]["brand_aliases"] == []
    assert snapshot.graph["entities"][0]["evidence"]["fact_revision_sha256"] in {"a" * 64, "b" * 64}
    assert snapshot.public_jsonld["@graph"]
    assert all("星河" not in item.get("alternateName", []) for item in snapshot.public_jsonld["@graph"])


def test_graph_event_chain_versions_updates_and_stale_facts_are_excluded() -> None:
    repository = create_repository()
    target = repository.create_entity(
        "tenant_graph", "project_graph",
        entity_payload(role="target", name="AIRank", revision_id="revision_target"),
        "reviewer_1", "trc_create",
    )
    updated = repository.update_entity(
        "tenant_graph", "project_graph", target.entity_id,
        entity_payload(role="target", name="AIRank 来客", revision_id="revision_target").model_copy(
            update={"expected_version": 1}
        ),
        "reviewer_2", "trc_update",
    )
    assert updated.version == 2
    with repository._engine.begin() as conn:
        events = conn.execute(text("""
            SELECT aggregate_version, previous_event_sha256, event_sha256
            FROM airank_brand_graph_events
            WHERE aggregate_id=:entity_id ORDER BY aggregate_version
        """), {"entity_id": target.entity_id}).mappings().all()
        assert events[0]["previous_event_sha256"] is None
        assert events[1]["previous_event_sha256"] == events[0]["event_sha256"]
        conn.execute(text("UPDATE airank_fact_revisions SET status='superseded' WHERE id='revision_target'"))

    snapshot = repository.compile_snapshot("tenant_graph", "project_graph", "reviewer_2")
    assert snapshot.status == "blocked"
    assert "records_with_stale_or_ineligible_evidence_were_excluded" in snapshot.known_limitations


def test_brand_graph_api_and_contracts(monkeypatch) -> None:
    repository = create_repository()
    monkeypatch.setattr(brand_graph_routes, "BRAND_GRAPH_REPOSITORY", repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
    client = TestClient(app)

    entity = client.post(
        "/api/v1/projects/project_graph/brand-entities",
        headers={"tenant-id": "tenant_graph", "X-AIRank-Trace-Id": "trc_graph_api"},
        json={
            "entity_role": "target",
            "entity_kind": "brand",
            "canonical_name": "AIRank",
            "website_url": "https://airank.example",
            "usage_scope": "public_and_measurement",
            "fact_revision_id": "revision_target",
        },
    )
    assert entity.status_code == 201

    compiled = client.post(
        "/api/v1/projects/project_graph/brand-graph/snapshots",
        headers={"tenant-id": "tenant_graph", "X-AIRank-Trace-Id": "trc_graph_compile"},
        json={"requested_by": "reviewer_1"},
    )
    assert compiled.status_code == 201
    assert compiled.json()["data"]["status"] == "governed"
    validate("brand_graph_snapshot_response.schema.json", compiled.json())

    portfolio = client.get(
        "/api/v1/projects/project_graph/brand-graph",
        headers={"tenant-id": "tenant_graph", "X-AIRank-Trace-Id": "trc_graph_portfolio"},
    )
    assert portfolio.status_code == 200
    assert portfolio.json()["data"]["measurement_ready"] is True
    validate("brand_graph_portfolio_response.schema.json", portfolio.json())


def test_brand_graph_request_contracts_are_strict() -> None:
    validate("brand_entity_write_request.schema.json", {
        "entity_role": "target", "entity_kind": "brand", "canonical_name": "AIRank",
        "usage_scope": "public_and_measurement", "fact_revision_id": "revision_target",
    })
    validate("brand_alias_write_request.schema.json", {
        "alias_text": "来客", "alias_type": "official", "fact_revision_id": "revision_target",
    })
    validate("brand_relation_write_request.schema.json", {
        "subject_entity_id": "brand_entity_target", "predicate": "competitor_of",
        "object_entity_id": "brand_entity_competitor", "fact_revision_id": "revision_target",
    })
    validate("brand_graph_compile_request.schema.json", {"requested_by": "reviewer_1"})


def test_brand_graph_write_uses_trusted_actor_and_permissions(monkeypatch) -> None:
    repository = create_repository()
    monkeypatch.setattr(brand_graph_routes, "BRAND_GRAPH_REPOSITORY", repository)
    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_graph")
    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "console:read")
    api_main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(app)

    ordinary_token = client.post(
        "/api/v1/auth/login",
        json={"username": "ordinary-user", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    forbidden = client.post(
        "/api/v1/projects/project_graph/brand-entities",
        headers={
            "tenant-id": "tenant_graph",
            "Authorization": f"Bearer {ordinary_token}",
            "X-AIRank-User-Id": "spoofed-admin",
            "X-AIRank-Permissions": "airank:knowledge:admin",
        },
        json={
            "entity_role": "target",
            "entity_kind": "brand",
            "canonical_name": "AIRank",
            "fact_revision_id": "revision_target",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "AUTH_PERMISSION_FORBIDDEN"

    monkeypatch.setenv("AIRANK_DEV_PERMISSIONS", "airank:knowledge:admin")
    admin_token = client.post(
        "/api/v1/auth/login",
        json={"username": "graph-admin", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]
    created = client.post(
        "/api/v1/projects/project_graph/brand-entities",
        headers={
            "tenant-id": "tenant_graph",
            "Authorization": f"Bearer {admin_token}",
            "X-AIRank-User-Id": "spoofed-actor",
        },
        json={
            "entity_role": "target",
            "entity_kind": "brand",
            "canonical_name": "AIRank",
            "fact_revision_id": "revision_target",
        },
    )
    assert created.status_code == 201
    assert created.json()["data"]["created_by"] == "graph-admin"
