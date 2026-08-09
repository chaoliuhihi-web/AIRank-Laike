from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_brand_graph_migration_is_versioned_evidence_bound_and_scan_frozen() -> None:
    migration = read("apps/api/alembic/versions/20260809_0039_governed_brand_graph.py")

    for required in (
        "airank_brand_entities",
        "airank_brand_entity_aliases",
        "airank_brand_relations",
        "airank_brand_graph_events",
        "airank_brand_graph_snapshots",
        "fact_revision_id",
        "evidence_manifest_sha256",
        "previous_event_sha256",
        "entity_graph_snapshot_id",
        "entity_graph_sha256",
        "entity_graph_status",
        "entity_graph_limitations_json",
    ):
        assert required in migration


def test_brand_graph_api_requires_fact_governance_and_exposes_snapshot_routes() -> None:
    routes = read("apps/api/brand_graph_routes.py")

    for required in (
        "airank.brand-graph.v1",
        "airank.brand-graph-compiler.v1",
        "BRAND_GRAPH_FACT_NOT_ELIGIBLE",
        "public_and_measurement",
        "measurement_only",
        "ambiguous_aliases",
        "legacy_unverified",
        "public_jsonld",
        '"/projects/{project_id}/brand-graph"',
        '"/projects/{project_id}/brand-entities"',
        '"/projects/{project_id}/brand-relations"',
        '"/projects/{project_id}/brand-graph/snapshots"',
        '"/brand-graph-snapshots/{snapshot_id}"',
    ):
        assert required in routes


def test_scan_execution_uses_immutable_graph_not_mutable_competitor_rows() -> None:
    main = read("apps/api/main.py")

    assert "entity_graph_snapshot_id" in main
    assert "entity_graph_sha256" in main
    assert "BRAND_GRAPH_BLOCKED" in main
    assert 'measurement_lexicon.get("competitors")' in main
    assert 'prompt_context.get("website_url")' in main
    assert 'prompt_context.get("industry")' in main

    completion = main.split("def complete_mysql_real_brand_scan", 1)[1].split("\ndef ", 1)[0]
    assert "list_competitors(" not in completion


def test_brand_graph_contracts_are_strict_and_scan_response_exposes_binding() -> None:
    contract_names = (
        "brand_entity_write_request.schema.json",
        "brand_alias_write_request.schema.json",
        "brand_relation_write_request.schema.json",
        "brand_graph_compile_request.schema.json",
        "brand_graph_snapshot_response.schema.json",
        "brand_graph_portfolio_response.schema.json",
    )
    for contract_name in contract_names:
        payload = json.loads(read(f"packages/contracts/{contract_name}"))
        assert payload.get("$schema") == "https://json-schema.org/draft/2020-12/schema"

    scan = json.loads(read("packages/contracts/scan_run_response.schema.json"))
    properties = scan["properties"]["data"]["properties"]
    assert properties["entity_graph_snapshot_id"]["type"] == ["string", "null"]
    assert properties["entity_graph_sha256"]["type"] == ["string", "null"]
    assert "legacy_unverified" in properties["entity_graph_status"]["enum"]


def test_brand_graph_is_registered_as_partial_internal_skill_and_matrix_capability() -> None:
    registry = json.loads(read("packages/skills/registry.json"))
    manifest = next(
        item for item in registry["skills"] if item["skill_id"] == "knowledge.entity-graph-compiler"
    )

    assert manifest["version"] == "1.0.0"
    assert manifest["status"] == "partial"
    assert manifest["failure_policy"]["ambiguous_target"] == "blocked"
    assert "fact_expiry_conflict_and_alias_ambiguity_integration" in manifest["promotion_policy"]["required_evidence"]

    matrix = read("docs/architecture/yaojingang-absorption-matrix.md")
    row = next(line for line in matrix.splitlines() if "`yao-geo-brand-graph`" in line and line.startswith("|"))
    assert "| adapt | Entity Graph Skill | P1 | partial |" in row
    assert "ScanRun/Task/Worker" in row
