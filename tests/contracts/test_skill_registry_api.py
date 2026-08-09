from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from apps.api import main as api_main
from apps.api.main import app


def test_admin_skill_registry_exposes_eleven_partial_internal_skills() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/admin/skills", headers={"X-AIRank-Trace-Id": "trc_skill_registry"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_skill_registry"
    assert len(body["data"]["skills"]) == 11
    assert {item["status"] for item in body["data"]["skills"]} == {"partial"}
    assert all(item["eval_cases"] for item in body["data"]["skills"])
    assert all(item["evaluation"]["local_eval_status"] == "passed" for item in body["data"]["skills"])
    assert all(item["evaluation"]["total_cases"] == 3 for item in body["data"]["skills"])
    assert all(item["evaluation"]["promotion_eligible"] is False for item in body["data"]["skills"])
    assert all(item["evaluation"]["promotion_blockers"] for item in body["data"]["skills"])
    assert all(item["trust"]["decision"] == "allow_local_execution" for item in body["data"]["skills"])
    assert all(item["trust_policy"]["network_access"]["mode"] == "deny" for item in body["data"]["skills"])


def test_admin_skill_eval_executes_versioned_runner() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/admin/skills/measurement.answer-parser/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_eval"},
        json={"input": {"answer_text": "推荐其他品牌。", "brand_name": "AIRank"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["skill_id"] == "measurement.answer-parser"
    assert body["data"]["version"] == "1.0.0"
    assert body["data"]["manifest_status"] == "partial"
    assert body["data"]["output"]["mention_class"] == "not_mentioned"


def test_admin_skill_eval_rejects_invalid_input_and_unknown_skill() -> None:
    client = TestClient(app)

    invalid = client.post(
        "/api/v1/admin/skills/measurement.answer-parser/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_invalid"},
        json={"input": {"answer_text": "missing brand"}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_FAILED"

    missing = client.post(
        "/api/v1/admin/skills/measurement.unknown/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_missing"},
        json={"input": {}},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SKILL_NOT_FOUND"


def test_admin_skill_promotion_ledger_is_hash_bound_and_does_not_auto_promote() -> None:
    response = TestClient(app).get(
        "/api/v1/admin/skills/promotion-ledger",
        headers={"X-AIRank-Trace-Id": "trc_skill_ledger"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["trace_id"] == "trc_skill_ledger"
    assert set(body["data"]["source_sha256"]) == {
        "registry",
        "registry_schema",
        "eval_corpus",
        "promotion_evidence",
        "implementation",
        "evaluation_engine",
        "trust_engine",
    }
    assert body["data"]["ledger_version"] == "1.1.0"
    assert len(body["data"]["trust_report_sha256"]) == 64
    assert body["data"]["native_runtime_enforcement"] is False
    assert len(body["data"]["skills"]) == 11
    assert {item["decision"] for item in body["data"]["skills"]} == {"retain_partial"}


def test_admin_skill_trust_report_matches_contract_and_keeps_native_boundary_explicit() -> None:
    response = TestClient(app).get(
        "/api/v1/admin/skills/trust-report",
        headers={"X-AIRank-Trace-Id": "trc_skill_trust"},
    )

    assert response.status_code == 200
    body = response.json()
    schema_path = Path(__file__).resolve().parents[2] / "packages" / "contracts" / "skill_trust_report_response.schema.json"
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(body)
    assert body["meta"]["trace_id"] == "trc_skill_trust"
    assert body["data"]["status"] == "passed"
    assert body["data"]["summary"]["execution_allowed_count"] == 11
    assert body["data"]["installation"]["status"] == "passed"
    assert body["data"]["native_runtime_enforcement"] is False


def test_admin_skill_eval_fails_closed_when_trust_gate_blocks(monkeypatch) -> None:
    class BlockedAudit:
        checks = ({"check_id": "declared_capability_boundary", "status": "failed"},)

    monkeypatch.setattr(api_main, "trust_allows_skill", lambda skill_id, registry: (False, BlockedAudit()))
    response = TestClient(app).post(
        "/api/v1/admin/skills/measurement.answer-parser/eval",
        headers={"X-AIRank-Trace-Id": "trc_skill_trust_blocked"},
        json={"input": {"answer_text": "推荐其他品牌。", "brand_name": "AIRank"}},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SKILL_TRUST_BLOCKED"
