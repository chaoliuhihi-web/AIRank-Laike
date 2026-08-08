from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import fact_acquisition_routes
from apps.api.fact_acquisition_routes import (
    GAP_CONTRACT_VERSION,
    TASK_CONTRACT_VERSION,
    FactAcquisitionTaskCreateRequest,
    GapSeed,
    InMemoryFactAcquisitionRepository,
    RevisionSeed,
    revision_has_exact_source_support,
)
from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "packages" / "contracts"


def validate_contract(name: str, payload: object) -> None:
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    ).validate(payload)


def governed_gap(*, contract_version: str = GAP_CONTRACT_VERSION) -> GapSeed:
    return GapSeed(
        gap_id="gap_ev_1234567890abcdef1234",
        project_id="project_fact_task",
        contract_version=contract_version,
        evidence_sha256="a" * 64,
        quality_report_sha256="b" * 64,
        severity="high",
        title="qianwen · API 未提及品牌",
        related_question_ids=("question_fact_task",),
        provider="qianwen",
        collector_surface="api",
        suggested_asset_type="comparison_page",
    )


def test_fact_acquisition_is_fail_closed_until_approved_evidence(monkeypatch) -> None:  # noqa: ANN001
    repository = InMemoryFactAcquisitionRepository()
    repository.seed_gap("tenant_fact_task", governed_gap())
    repository.seed_revision(
        "tenant_fact_task",
        "project_fact_task",
        RevisionSeed(
            revision_id="fact_revision_pending",
            fact_atom_id="fact_pending",
            status="proposed",
            source_ids=("knowledge_source_official",),
            eligible=False,
        ),
    )
    monkeypatch.setattr(
        fact_acquisition_routes,
        "FACT_ACQUISITION_REPOSITORY",
        repository,
    )
    client = TestClient(app)
    common_headers = {
        "tenant-id": "tenant_fact_task",
        "X-AIRank-User-Id": "trusted-knowledge-operator",
    }

    created = client.post(
        "/api/v1/projects/project_fact_task/evidence-gaps/gap_ev_1234567890abcdef1234/fact-acquisition-tasks",
        headers={
            **common_headers,
            "X-AIRank-Trace-Id": "trc_fact_task_create",
            "Idempotency-Key": "fact-task-create-1",
        },
        json={"requested_by": "spoofed-operator"},
    )
    assert created.status_code == 201
    task = created.json()["data"]
    assert task["contract_version"] == TASK_CONTRACT_VERSION
    assert task["status"] == "open"
    assert task["resolution_state"] == "needs_fact_proposal"
    assert task["generation_allowed"] is False
    assert task["created_by"] == "trusted-knowledge-operator"
    assert task["gap_evidence_sha256"] == "a" * 64
    assert task["event_count"] == 1
    validate_contract("fact_acquisition_task_response.schema.json", created.json())

    pending = client.post(
        f"/api/v1/projects/project_fact_task/fact-acquisition-tasks/{task['task_id']}/evidence-bindings",
        headers={
            **common_headers,
            "Idempotency-Key": "fact-task-bind-pending",
        },
        json={
            "fact_revision_ids": ["fact_revision_pending"],
            "expected_version": 1,
            "requested_by": "spoofed-operator",
        },
    )
    assert pending.status_code == 201
    pending_task = pending.json()["data"]
    assert pending_task["status"] == "in_review"
    assert pending_task["resolution_state"] == "needs_fact_review"
    assert pending_task["approved_fact_revision_ids"] == []
    assert pending_task["generation_allowed"] is False
    assert pending_task["event_count"] == 2
    validate_contract("fact_acquisition_task_response.schema.json", pending.json())

    stale = client.post(
        f"/api/v1/projects/project_fact_task/fact-acquisition-tasks/{task['task_id']}/evidence-bindings",
        headers={
            **common_headers,
            "Idempotency-Key": "fact-task-bind-stale",
        },
        json={
            "fact_revision_ids": ["fact_revision_pending"],
            "expected_version": 1,
            "requested_by": "spoofed-operator",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "FACT_ACQUISITION_TASK_VERSION_CONFLICT"

    repository.seed_revision(
        "tenant_fact_task",
        "project_fact_task",
        RevisionSeed(
            revision_id="fact_revision_pending",
            fact_atom_id="fact_pending",
            status="approved",
            source_ids=("knowledge_source_official",),
            eligible=True,
        ),
    )
    resolved = client.post(
        f"/api/v1/projects/project_fact_task/fact-acquisition-tasks/{task['task_id']}/evidence-bindings",
        headers={
            **common_headers,
            "Idempotency-Key": "fact-task-bind-approved",
        },
        json={
            "fact_revision_ids": ["fact_revision_pending"],
            "expected_version": 2,
            "requested_by": "spoofed-operator",
        },
    )
    assert resolved.status_code == 201
    resolved_task = resolved.json()["data"]
    assert resolved_task["status"] == "resolved"
    assert resolved_task["resolution_state"] == "ready_for_intervention"
    assert resolved_task["approved_fact_revision_ids"] == ["fact_revision_pending"]
    assert resolved_task["generation_allowed"] is True
    assert resolved_task["event_count"] == 3
    assert len(resolved_task["last_event_sha256"]) == 64

    replay = client.post(
        f"/api/v1/projects/project_fact_task/fact-acquisition-tasks/{task['task_id']}/evidence-bindings",
        headers={
            **common_headers,
            "Idempotency-Key": "fact-task-bind-approved",
        },
        json={
            "fact_revision_ids": ["fact_revision_pending"],
            "expected_version": 2,
            "requested_by": "spoofed-operator",
        },
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["idempotent_replay"] is True
    assert replay.json()["data"]["event_count"] == 3

    listed = client.get(
        "/api/v1/projects/project_fact_task/fact-acquisition-tasks",
        headers={"tenant-id": "tenant_fact_task"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["resolved_count"] == 1
    validate_contract("fact_acquisition_task_list_response.schema.json", listed.json())


def test_unverified_or_already_evidenced_gap_cannot_create_task() -> None:
    repository = InMemoryFactAcquisitionRepository()
    legacy = governed_gap(contract_version="legacy")
    repository.seed_gap("tenant_fact_task", legacy)

    with pytest.raises(StarletteHTTPException) as exc_info:
        repository.create_task(
            "tenant_fact_task",
            "project_fact_task",
            legacy.gap_id,
            FactAcquisitionTaskCreateRequest(requested_by="operator"),
            idempotency_key="fact-task-legacy",
            actor="operator",
            trace_id="trc_fact_task_legacy",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "FACT_ACQUISITION_GAP_INELIGIBLE"


def test_fact_acquisition_request_contracts_are_strict() -> None:
    validate_contract(
        "fact_acquisition_task_create_request.schema.json",
        {"requested_by": "operator", "evidence_requirement": "需要官方产品文档的精确原文。"},
    )
    validate_contract(
        "fact_acquisition_evidence_bind_request.schema.json",
        {
            "fact_revision_ids": ["fact_revision_1"],
            "expected_version": 1,
            "requested_by": "operator",
        },
    )


def test_exact_source_boundary_and_content_hash_are_required() -> None:
    content = "AIRank 保存不可变回答，并允许指标下钻到样本。"
    content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    revision = {
        "id": "fact_revision_exact",
        "fact_text": "AIRank 保存不可变回答",
        "source_ids_json": ["source_exact"],
    }
    source = {
        "id": "source_exact",
        "content_text": content,
        "content_sha256": content_sha256,
        "source_content_sha256": content_sha256,
    }

    assert revision_has_exact_source_support(revision, {"source_exact": source}) is True
    assert revision_has_exact_source_support(
        {**revision, "fact_text": "来源中不存在的营销结论"},
        {"source_exact": source},
    ) is False
    assert revision_has_exact_source_support(
        revision,
        {"source_exact": {**source, "source_content_sha256": "0" * 64}},
    ) is False
