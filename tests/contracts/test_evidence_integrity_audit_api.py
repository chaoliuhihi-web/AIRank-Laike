from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest
from sqlalchemy import text

from apps.api import evidence_integrity_routes
from apps.api.main import app
from airank_evidence import FilesystemObjectStorage


def _sha(value: str | bytes) -> str:
    payload = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _create_tables(repository: evidence_integrity_routes.MySQLEvidenceIntegrityRepository) -> None:
    statements = (
        "CREATE TABLE airank_projects (id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, deleted_at TEXT NULL)",
        "CREATE TABLE airank_answer_snapshots (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, sample_status TEXT, answer_text TEXT, answer_sha256 TEXT, raw_response_sha256 TEXT)",
        "CREATE TABLE airank_evidence_snapshots (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, answer_snapshot_id TEXT, raw_response_json TEXT, raw_response_sha256 TEXT)",
        "CREATE TABLE airank_citation_source_captures (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, status TEXT, response_bytes INTEGER, content_sha256 TEXT, visible_text_sha256 TEXT, raw_object_ref_id TEXT, text_object_ref_id TEXT)",
        "CREATE TABLE airank_citation_source_segments (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, capture_id TEXT, source_start INTEGER, source_end INTEGER, segment_text TEXT, segment_sha256 TEXT)",
        "CREATE TABLE airank_knowledge_source_contents (knowledge_source_id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, content_text TEXT, content_sha256 TEXT, byte_size INTEGER)",
        "CREATE TABLE airank_knowledge_segments (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, knowledge_source_id TEXT, segment_text TEXT, source_start INTEGER, source_end INTEGER, content_sha256 TEXT)",
        "CREATE TABLE airank_fact_revisions (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, fact_text TEXT, content_sha256 TEXT)",
        "CREATE TABLE airank_object_refs (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, object_type TEXT, byte_size INTEGER, sha256 TEXT, metadata_json TEXT)",
        "CREATE TABLE airank_scan_runs (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, status TEXT, metrics_json TEXT, deleted_at TEXT)",
        "CREATE TABLE airank_scan_tasks (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, run_id TEXT)",
        "CREATE TABLE airank_reports (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, report_type TEXT, status TEXT, run_id TEXT, retest_run_id TEXT, metrics_json TEXT, report_sha256 TEXT, evidence_index_json TEXT, generated_at TEXT, deleted_at TEXT)",
        "CREATE TABLE airank_retest_runs (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, baseline_run_id TEXT, compare_run_id TEXT, summary_json TEXT, observation_window_id TEXT)",
        "CREATE TABLE airank_retest_observation_windows (id TEXT PRIMARY KEY, tenant_id TEXT, window_label TEXT, package_id TEXT, baseline_run_id TEXT, compare_run_id TEXT, result_json TEXT)",
        "CREATE TABLE airank_evidence_integrity_audits (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, policy_version TEXT, scope TEXT, status TEXT, entity_count INTEGER, verified_count INTEGER, blocking_finding_count INTEGER, unavailable_count INTEGER, hash_mismatch_count INTEGER, size_mismatch_count INTEGER, metadata_invalid_count INTEGER, manifest_sha256 TEXT, idempotency_key TEXT, request_sha256 TEXT, requested_by TEXT, trace_id TEXT, started_at TEXT, completed_at TEXT, created_at TEXT, UNIQUE (tenant_id, project_id, idempotency_key))",
        "CREATE TABLE airank_evidence_integrity_findings (id TEXT PRIMARY KEY, audit_id TEXT, tenant_id TEXT, project_id TEXT, entity_type TEXT, entity_id TEXT, object_type TEXT, status TEXT, blocking INTEGER, expected_sha256 TEXT, actual_sha256 TEXT, expected_byte_size INTEGER, actual_byte_size INTEGER, details_json TEXT, created_at TEXT, UNIQUE (audit_id, entity_type, entity_id))",
        "CREATE TABLE airank_audit_events (id TEXT PRIMARY KEY, tenant_id TEXT, project_id TEXT, event_type TEXT, entity_type TEXT, entity_id TEXT, trace_id TEXT, payload_json TEXT, created_at TEXT)",
    )
    with repository._engine.begin() as conn:
        for statement in statements:
            conn.exec_driver_sql(statement)


def _seed_valid_project(
    repository: evidence_integrity_routes.MySQLEvidenceIntegrityRepository,
    storage: FilesystemObjectStorage,
) -> tuple[str, str]:
    tenant_id = "tenant_integrity"
    project_id = "project_integrity"
    answer_text = "AIRank keeps unmentioned samples in the denominator."
    raw_json = '{"request_id":"req-real","answer":"ok"}'
    raw_page = b"<html><body>Verified source text.</body></html>"
    visible_text = "Verified source text."
    segment_text = "source text"
    segment_start = visible_text.index(segment_text)
    knowledge_text = "AIRank uses immutable evidence snapshots."
    knowledge_segment = "immutable evidence"
    knowledge_start = knowledge_text.index(knowledge_segment)
    fact_text = "AIRank preserves valid unmentioned samples."
    raw_object = storage.put_bytes(raw_page, key="captures/raw.html", content_type="text/html")
    text_object = storage.put_bytes(visible_text.encode(), key="captures/text.txt", content_type="text/plain")
    with repository._engine.begin() as conn:
        conn.execute(text("INSERT INTO airank_projects VALUES (:id, :tenant, NULL)"), {"id": project_id, "tenant": tenant_id})
        conn.execute(
            text("INSERT INTO airank_answer_snapshots VALUES ('snapshot_1', :tenant, :project, 'valid', :answer, :answer_sha, :raw_sha)"),
            {"tenant": tenant_id, "project": project_id, "answer": answer_text, "answer_sha": _sha(answer_text), "raw_sha": _sha(raw_json)},
        )
        conn.execute(
            text("INSERT INTO airank_evidence_snapshots VALUES ('evidence_1', :tenant, :project, 'snapshot_1', :raw_json, :raw_sha)"),
            {"tenant": tenant_id, "project": project_id, "raw_json": raw_json, "raw_sha": _sha(raw_json)},
        )
        for object_id, object_type, stored in (
            ("object_raw", "citation_source_raw", raw_object),
            ("object_text", "citation_source_text", text_object),
        ):
            conn.execute(
                text("INSERT INTO airank_object_refs VALUES (:id, :tenant, :project, :type, :size, :sha, :metadata)"),
                {
                    "id": object_id,
                    "tenant": tenant_id,
                    "project": project_id,
                    "type": object_type,
                    "size": stored.byte_size,
                    "sha": stored.sha256,
                    "metadata": json.dumps({"object_key": stored.key, "storage_driver": stored.driver, "immutable": True}),
                },
            )
        conn.execute(
            text("INSERT INTO airank_citation_source_captures VALUES ('capture_1', :tenant, :project, 'completed', :size, :raw_sha, :text_sha, 'object_raw', 'object_text')"),
            {"tenant": tenant_id, "project": project_id, "size": len(raw_page), "raw_sha": _sha(raw_page), "text_sha": _sha(visible_text)},
        )
        conn.execute(
            text("INSERT INTO airank_citation_source_segments VALUES ('citation_segment_1', :tenant, :project, 'capture_1', :start, :end, :segment, :sha)"),
            {"tenant": tenant_id, "project": project_id, "start": segment_start, "end": segment_start + len(segment_text), "segment": segment_text, "sha": _sha(segment_text)},
        )
        conn.execute(
            text("INSERT INTO airank_knowledge_source_contents VALUES ('source_1', :tenant, :project, :content, :sha, :size)"),
            {"tenant": tenant_id, "project": project_id, "content": knowledge_text, "sha": _sha(knowledge_text), "size": len(knowledge_text.encode())},
        )
        conn.execute(
            text("INSERT INTO airank_knowledge_segments VALUES ('knowledge_segment_1', :tenant, :project, 'source_1', :segment, :start, :end, :sha)"),
            {"tenant": tenant_id, "project": project_id, "segment": knowledge_segment, "start": knowledge_start, "end": knowledge_start + len(knowledge_segment), "sha": _sha(knowledge_segment)},
        )
        conn.execute(
            text("INSERT INTO airank_fact_revisions VALUES ('factrev_1', :tenant, :project, :fact, :sha)"),
            {"tenant": tenant_id, "project": project_id, "fact": fact_text, "sha": _sha(fact_text)},
        )
    return tenant_id, project_id


def test_integrity_audit_route_is_tenant_scoped_and_does_not_fake_an_empty_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = evidence_integrity_routes.InMemoryEvidenceIntegrityRepository()
    repository.seed_project("tenant_integrity", "project_integrity")
    monkeypatch.setattr(evidence_integrity_routes, "EVIDENCE_INTEGRITY_REPOSITORY", repository)
    client = TestClient(app)

    created = client.post(
        "/api/v1/projects/project_integrity/evidence-integrity-audits",
        headers={
            "tenant-id": "tenant_integrity",
            "X-AIRank-User-Id": "auditor_one",
            "Idempotency-Key": "integrity-empty-project",
            "X-AIRank-Trace-Id": "trc_integrity_empty",
        },
        json={"scope": "project"},
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["status"] == "blocked"
    assert data["blocking_finding_count"] == 1
    assert data["findings"][0]["details"]["reason"] == "no_evidence_entities"
    assert data["requested_by"] == "auditor_one"

    latest = client.get(
        "/api/v1/projects/project_integrity/evidence-integrity-audits/latest",
        headers={"tenant-id": "tenant_integrity"},
    )
    assert latest.status_code == 200
    assert latest.json()["data"]["audit_id"] == data["audit_id"]

    foreign = client.get(
        f"/api/v1/projects/project_integrity/evidence-integrity-audits/{data['audit_id']}",
        headers={"tenant-id": "tenant_other"},
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "EVIDENCE_INTEGRITY_AUDIT_NOT_FOUND"


def test_mysql_integrity_audit_verifies_every_entity_and_detects_tampering(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    repository = evidence_integrity_routes.MySQLEvidenceIntegrityRepository(
        "sqlite+pysqlite:///:memory:", object_storage=storage
    )
    _create_tables(repository)
    tenant_id, project_id = _seed_valid_project(repository, storage)

    def unexpected_storage_access() -> FilesystemObjectStorage:
        raise AssertionError("entity limit must be checked before object payloads are loaded")

    capped_repository = evidence_integrity_routes.MySQLEvidenceIntegrityRepository(
        engine=repository._engine,
        object_storage_factory=unexpected_storage_access,
        max_project_entities=8,
    )
    capped = capped_repository.run(
        tenant_id,
        project_id,
        idempotency_key="integrity-cap-v1",
        requested_by="auditor_one",
        trace_id="trc_integrity_cap",
    )
    assert capped.status == "blocked"
    assert capped.findings[0].status == "scope_too_large"
    assert capped.findings[0].details["entity_count"] == 9

    passed = repository.run(
        tenant_id,
        project_id,
        idempotency_key="integrity-valid-v1",
        requested_by="auditor_one",
        trace_id="trc_integrity_valid",
    )
    assert passed.status == "passed"
    assert passed.entity_count == 9
    assert passed.verified_count == 9
    assert passed.blocking_finding_count == 0
    assert len(passed.manifest_sha256) == 64
    replay = repository.run(
        tenant_id,
        project_id,
        idempotency_key="integrity-valid-v1",
        requested_by="auditor_one",
        trace_id="trc_integrity_replay",
    )
    assert replay.audit_id == passed.audit_id
    assert replay.idempotent_replay is True

    with repository._engine.begin() as conn:
        conn.execute(text("UPDATE airank_answer_snapshots SET answer_text='tampered' WHERE id='snapshot_1'"))
    storage.delete("captures/text.txt")

    blocked = repository.run(
        tenant_id,
        project_id,
        idempotency_key="integrity-tampered-v2",
        requested_by="auditor_one",
        trace_id="trc_integrity_tampered",
    )
    statuses = {(item.entity_type, item.entity_id): item.status for item in blocked.findings}
    assert blocked.status == "blocked"
    assert blocked.blocking_finding_count >= 3
    assert statuses[("answer_snapshot", "snapshot_1")] == "hash_mismatch"
    assert statuses[("object_ref", "object_text")] == "unavailable"
    assert statuses[("citation_segment", "citation_segment_1")] == "unavailable"


def test_integrity_response_matches_public_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = evidence_integrity_routes.InMemoryEvidenceIntegrityRepository()
    repository.seed_project("tenant_integrity", "project_integrity")
    monkeypatch.setattr(evidence_integrity_routes, "EVIDENCE_INTEGRITY_REPOSITORY", repository)
    response = TestClient(app).post(
        "/api/v1/projects/project_integrity/evidence-integrity-audits",
        headers={
            "tenant-id": "tenant_integrity",
            "X-AIRank-User-Id": "auditor_one",
            "Idempotency-Key": "integrity-contract-v1",
        },
        json={"scope": "project"},
    )
    schema = json.loads(
        Path("packages/contracts/evidence_integrity_audit_response.schema.json").read_text()
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(response.json())
