from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]


def validate_contract(schema_name: str, payload: dict) -> None:
    schema = json.loads((ROOT / "packages" / "contracts" / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


def _headers(tenant_id: str, trace_id: str) -> dict[str, str]:
    return {"tenant-id": tenant_id, "X-AIRank-Trace-Id": trace_id}


def test_question_map_compiles_deduplicates_persists_and_requires_review() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qgov_{uuid4().hex[:10]}"
    project = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qgov_project"),
        json={"website_url": "https://airank-question.example", "brand_name_hint": "AIRank"},
    ).json()["data"]

    payload = {
        "product_terms": ["GEO 平台"],
        "competitor_names": ["竞品甲"],
        "regions": ["北京"],
        "seed_questions": ["企业怎么选 GEO 平台？", " 企业怎么选GEO平台! "],
        "include_template_candidates": True,
        "persist": True,
        "created_by": "reviewer_qgov",
    }
    compiled = client.post(
        f"/api/v1/projects/{project['project_id']}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qgov_compile"),
        json=payload,
    )

    assert compiled.status_code == 201, compiled.text
    data = compiled.json()["data"]
    assert data["taxonomy_version"] == "airank-question-taxonomy-v1.2.0"
    assert data["duplicate_count"] >= 1
    assert data["persisted_count"] == data["question_count"]
    assert {item["cohort_type"] for item in data["questions"]} >= {"blind", "comparison"}
    assert all(item["observed_query"] is False for item in data["questions"])
    assert all(item["status"] == "suggested" for item in data["questions"])

    replay = client.post(
        f"/api/v1/projects/{project['project_id']}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qgov_replay"),
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["idempotent_replay"] is True
    assert replay.json()["data"]["map_version_id"] == data["map_version_id"]

    questions = client.get(
        f"/api/v1/projects/{project['project_id']}/buyer-questions",
        headers=_headers(tenant_id, "trc_qgov_questions"),
    ).json()["data"]
    assert len(questions) == data["persisted_count"]
    question = questions[0]
    assert question["status"] == "suggested"
    assert question["question_version_id"].startswith("question_v_")

    reviewed = client.patch(
        f"/api/v1/projects/{project['project_id']}/buyer-questions/{question['question_id']}/review",
        headers=_headers(tenant_id, "trc_qgov_review"),
        json={"action": "confirmed", "reviewed_by": "reviewer_qgov", "review_note": "问题意图与目标客户一致。"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["data"]["eligible_for_measurement"] is True

    refreshed = client.get(
        f"/api/v1/projects/{project['project_id']}/buyer-questions",
        headers=_headers(tenant_id, "trc_qgov_refreshed"),
    ).json()["data"]
    confirmed = next(item for item in refreshed if item["question_id"] == question["question_id"])
    assert confirmed["status"] == "confirmed"
    assert confirmed["reviewed_by"] == "reviewer_qgov"

    foreign = client.get(
        f"/api/v1/projects/{project['project_id']}/question-maps",
        headers=_headers("tenant_qgov_foreign", "trc_qgov_foreign"),
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_question_map_preview_does_not_persist_candidates() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qpreview_{uuid4().hex[:10]}"
    project_id = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qpreview_project"),
        json={"website_url": "https://preview-question.example", "brand_name_hint": "PreviewBrand"},
    ).json()["data"]["project_id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qpreview_compile"),
        json={
            "seed_questions": ["企业如何选择 GEO 服务商？"],
            "include_template_candidates": False,
            "persist": False,
            "created_by": "reviewer_preview",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "preview"
    assert response.json()["data"]["persisted_count"] == 0
    questions = client.get(
        f"/api/v1/projects/{project_id}/buyer-questions",
        headers=_headers(tenant_id, "trc_qpreview_questions"),
    )
    assert questions.status_code == 200
    assert questions.json()["data"] == []


def test_observation_batch_is_immutable_pii_safe_and_compiles_as_attested_query() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qobs_{uuid4().hex[:10]}"
    project_id = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qobs_project"),
        json={"website_url": "https://observed-question.example", "brand_name_hint": "ObservedBrand"},
    ).json()["data"]["project_id"]
    payload = {
        "source_type": "site_search",
        "source_name": "官网站内搜索导出 2026-08",
        "date_range_start": "2026-08-01T00:00:00Z",
        "date_range_end": "2026-08-07T23:59:59Z",
        "records": [
            {
                "source_record_id": "search-1",
                "question_text": "制造企业怎么选择 GEO 平台？",
                "occurrence_count": 7,
                "observed_at": "2026-08-06T09:30:00Z",
                "region": "上海",
            },
            {
                "source_record_id": "search-2",
                "question_text": "请联系 buyer@example.com 了解 GEO 价格",
                "occurrence_count": 1,
            },
        ],
        "rights_attested": True,
        "imported_by": "researcher_qobs",
    }
    imported = client.post(
        f"/api/v1/projects/{project_id}/question-observation-batches",
        headers=_headers(tenant_id, "trc_qobs_import"),
        json=payload,
    )

    assert imported.status_code == 201, imported.text
    validate_contract("question_observation_import_request.schema.json", payload)
    validate_contract("question_observation_import_response.schema.json", imported.json())
    data = imported.json()["data"]
    batch = data["batch"]
    assert batch["access_mode"] == "user_provided"
    assert batch["evidence_grade"] == "user_provided_snapshot"
    assert batch["record_count"] == 1
    assert batch["occurrence_count"] == 7
    assert batch["pii_blocked_count"] == 1
    assert batch["blocked_records"][0]["reasons"] == ["email"]
    assert "buyer@example.com" not in imported.text
    assert len(data["records"]) == 1

    replay = client.post(
        f"/api/v1/projects/{project_id}/question-observation-batches",
        headers=_headers(tenant_id, "trc_qobs_replay"),
        json=payload,
    )
    assert replay.status_code == 201
    assert replay.json()["data"]["batch"]["idempotent_replay"] is True
    assert replay.json()["data"]["batch"]["batch_id"] == batch["batch_id"]

    compiled = client.post(
        f"/api/v1/projects/{project_id}/question-maps/compile",
        headers=_headers(tenant_id, "trc_qobs_compile"),
        json={
            "observation_batch_ids": [batch["batch_id"]],
            "include_template_candidates": False,
            "persist": True,
            "created_by": "researcher_qobs",
        },
    )
    assert compiled.status_code == 201, compiled.text
    candidate = compiled.json()["data"]["questions"][0]
    assert candidate["source_kind"] == "observed_query"
    assert candidate["observed_query"] is True
    assert candidate["provenance_records"][0]["occurrence_count"] == 7
    assert candidate["provenance_records"][0]["evidence_grade"] == "user_provided_snapshot"

    records = client.get(
        f"/api/v1/projects/{project_id}/question-observation-batches/{batch['batch_id']}/records",
        headers=_headers(tenant_id, "trc_qobs_records"),
    )
    assert records.status_code == 200
    assert len(records.json()["data"]) == 1


def test_observation_import_requires_rights_attestation() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qobs_rights_{uuid4().hex[:10]}"
    project_id = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qobs_rights_project"),
        json={"website_url": "https://observed-rights.example", "brand_name_hint": "RightsBrand"},
    ).json()["data"]["project_id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/question-observation-batches",
        headers=_headers(tenant_id, "trc_qobs_rights"),
        json={
            "source_type": "customer_support",
            "source_name": "客服问题",
            "records": [{"question_text": "企业怎么选择 GEO 服务？"}],
            "rights_attested": False,
            "imported_by": "researcher_qobs",
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_observation_import_blocks_pii_in_record_metadata_and_resolved_id_collisions() -> None:
    client = TestClient(app)
    tenant_id = f"tenant_qobs_metadata_{uuid4().hex[:10]}"
    project_id = client.post(
        "/api/v1/projects",
        headers=_headers(tenant_id, "trc_qobs_metadata_project"),
        json={"website_url": "https://observed-metadata.example", "brand_name_hint": "MetadataBrand"},
    ).json()["data"]["project_id"]

    blocked = client.post(
        f"/api/v1/projects/{project_id}/question-observation-batches",
        headers=_headers(tenant_id, "trc_qobs_metadata_pii"),
        json={
            "source_type": "customer_support",
            "source_name": "客服问题",
            "records": [
                {
                    "source_record_id": "buyer@example.com",
                    "question_text": "企业如何选择 GEO 服务？",
                }
            ],
            "rights_attested": True,
            "imported_by": "researcher_qobs",
        },
    )
    assert blocked.status_code == 201
    assert blocked.json()["data"]["batch"]["status"] == "blocked"
    assert blocked.json()["data"]["batch"]["pii_blocked_count"] == 1
    assert blocked.json()["data"]["records"] == []
    assert "buyer@example.com" not in blocked.text

    collision = client.post(
        f"/api/v1/projects/{project_id}/question-observation-batches",
        headers=_headers(tenant_id, "trc_qobs_metadata_collision"),
        json={
            "source_type": "site_search",
            "source_name": "站内搜索",
            "records": [
                {"question_text": "企业如何选择 GEO 服务？"},
                {"source_record_id": "row:1", "question_text": "GEO 服务如何保留原始证据？"},
            ],
            "rights_attested": True,
            "imported_by": "researcher_qobs",
        },
    )
    assert collision.status_code == 422
    assert collision.json()["error"]["code"] == "VALIDATION_FAILED"
