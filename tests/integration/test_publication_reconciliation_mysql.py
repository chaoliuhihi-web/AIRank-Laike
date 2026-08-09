from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_evidence import build_object_storage_from_env
from apps.api.operation_guard import MySQLOperationGuard
from apps.api.publication_reconciliation import (
    MySQLPublicationReconciliationRepository,
    PublicationReconciliationReviewRequest,
    PublicationReconciliationSubmitRequest,
)


DEFAULT_MYSQL_URL = "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4"


def database_url() -> str:
    return os.getenv("AIRANK_DATABASE_URL", DEFAULT_MYSQL_URL)


def cleanup_tenant(engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                r"""
                SELECT table_name FROM information_schema.columns
                WHERE table_schema=DATABASE() AND column_name='tenant_id'
                  AND table_name LIKE 'airank\_%'
                ORDER BY table_name DESC
                """
            )
        ).scalars().all()
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        try:
            for table_name in tables:
                conn.execute(text(f"DELETE FROM `{table_name}` WHERE tenant_id=:tenant_id"), {"tenant_id": tenant_id})
        finally:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def test_real_mysql_two_person_reconciliation_atomically_closes_local_ledgers(tmp_path, monkeypatch) -> None:
    if os.getenv("AIRANK_RUN_REAL_MYSQL") != "1":
        pytest.skip("set AIRANK_RUN_REAL_MYSQL=1 to run real publication reconciliation integration")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "local")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(tmp_path / "objects"))
    suffix = uuid4().hex[:10]
    tenant_id = f"tenant_publish_recon_{suffix}"
    project_id = f"project_publish_recon_{suffix}"
    asset_id = f"asset_publish_recon_{suffix}"
    review_id = f"review_publish_recon_{suffix}"
    snapshot_id = f"snapshot_publish_recon_{suffix}"
    package_id = f"package_publish_recon_{suffix}"
    attempt_id = f"publish_attempt_{suffix}aa"
    now = datetime.now(timezone.utc)
    request_sha256 = "b" * 64
    engine = create_engine(database_url(), pool_pre_ping=True)
    guard = MySQLOperationGuard(database_url())
    repository = MySQLPublicationReconciliationRepository(database_url())
    storage = build_object_storage_from_env()
    evidence = storage.put_bytes(
        b"immutable customer publication receipt and screenshot evidence",
        key=f"publication-reconciliation/{tenant_id}/receipt.txt",
        content_type="text/plain",
    )
    object_ref_id = f"object_publish_recon_{suffix}"

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO airank_projects (id,tenant_id,name,brand_name,status,created_by) VALUES (:id,:tenant_id,'Reconciliation QA','Reconciliation QA','active','integration')"),
                {"id": project_id, "tenant_id": tenant_id},
            )
            conn.execute(
                text("INSERT INTO airank_content_assets (id,tenant_id,project_id,asset_type,title,body_md,content_sha256,status,created_at,updated_at) VALUES (:id,:tenant_id,:project_id,'fact_page','Evidence page','Evidence body',:sha,'approved',:now,:now)"),
                {"id": asset_id, "tenant_id": tenant_id, "project_id": project_id, "sha": "c" * 64, "now": now},
            )
            conn.execute(
                text("INSERT INTO airank_content_reviews (id,tenant_id,project_id,asset_id,content_sha256,action,fact_check_status,risk_level,risk_findings_json,reviewed_by,reviewed_at) VALUES (:id,:tenant_id,:project_id,:asset_id,:sha,'approved','passed','low','[]','content-reviewer',:now)"),
                {"id": review_id, "tenant_id": tenant_id, "project_id": project_id, "asset_id": asset_id, "sha": "c" * 64, "now": now},
            )
            conn.execute(
                text("INSERT INTO airank_publish_snapshots (id,tenant_id,project_id,asset_id,content_review_id,snapshot_version,title,body_md,content_sha256,manifest_json,created_by,created_at) VALUES (:id,:tenant_id,:project_id,:asset_id,:review_id,1,'Evidence page','Evidence body',:sha,'{}','publisher',:now)"),
                {"id": snapshot_id, "tenant_id": tenant_id, "project_id": project_id, "asset_id": asset_id, "review_id": review_id, "sha": "c" * 64, "now": now},
            )
            conn.execute(
                text("INSERT INTO airank_publish_packages (id,tenant_id,project_id,asset_id,snapshot_id,content_review_id,idempotency_key,package_type,channel,status,metadata_json,publication_action,requested_by,created_at,updated_at) VALUES (:id,:tenant_id,:project_id,:asset_id,:snapshot_id,:review_id,:key,'content_asset','http','outcome_unknown',:metadata,'publish','publisher',:now,:now)"),
                {"id": package_id, "tenant_id": tenant_id, "project_id": project_id, "asset_id": asset_id, "snapshot_id": snapshot_id, "review_id": review_id, "key": f"publish-reconciliation-{suffix}", "metadata": json.dumps({"content_sha256": "c" * 64, "implementation_status": "partial", "reconciliation_required": True}), "now": now},
            )
            conn.execute(
                text("INSERT INTO airank_object_refs (id,tenant_id,project_id,object_type,object_uri,content_type,byte_size,sha256,metadata_json,created_at) VALUES (:id,:tenant_id,:project_id,'publication_reconciliation_evidence',:uri,:content_type,:byte_size,:sha,:metadata,:now)"),
                {"id": object_ref_id, "tenant_id": tenant_id, "project_id": project_id, "uri": evidence.uri, "content_type": evidence.content_type, "byte_size": evidence.byte_size, "sha": evidence.sha256, "metadata": json.dumps({"immutable": True, "object_key": evidence.key, "storage_driver": evidence.driver}), "now": now},
            )

        claim = guard.claim(
            tenant_id=tenant_id,
            operation_type="publisher.publish",
            resource_key=package_id,
            idempotency_key=f"publish-reconciliation-{suffix}",
            request_sha256=request_sha256,
            request_key_id=None,
            actor="publisher-worker",
            trace_id="job-lost-response",
        )
        guard.mark_external_started(claim.operation_id, "publisher-worker", "job-lost-response")
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO airank_publish_attempts (id,tenant_id,project_id,package_id,attempt_number,channel,status,request_sha256,operation_id,error_code,error_message,started_at,finished_at,created_at) VALUES (:id,:tenant_id,:project_id,:package_id,1,'http','outcome_unknown',:request_sha,:operation_id,'PUBLISH_NETWORK_FAILED','response was lost after request write',:started_at,:finished_at,:created_at)"),
                {"id": attempt_id, "tenant_id": tenant_id, "project_id": project_id, "package_id": package_id, "request_sha": request_sha256, "operation_id": claim.operation_id, "started_at": now - timedelta(minutes=3), "finished_at": now - timedelta(minutes=2), "created_at": now - timedelta(minutes=3)},
            )

        submitted = repository.submit(
            tenant_id,
            package_id,
            PublicationReconciliationSubmitRequest(
                published_url="https://customer.example/evidence/reconciled",
                external_receipt_id="customer-receipt-77",
                response_status=201,
                evidence_object_ref_id=object_ref_id,
                evidence_sha256=evidence.sha256,
                evidence_note="客户后台回执和不可变页面证据显示该请求已成功创建远端内容。",
                observed_at=now - timedelta(minutes=1),
                submitted_by="delivery-submitter",
                idempotency_key=f"reconciliation-case-{suffix}",
            ),
            "trc_reconciliation_submit",
        )
        assert submitted.status == "awaiting_review"

        with pytest.raises(StarletteHTTPException) as self_review:
            repository.review(
                tenant_id,
                submitted.case_id,
                PublicationReconciliationReviewRequest(
                    action="approved",
                    reviewed_by="delivery-submitter",
                    review_note="提交人不能自行确认这条证据。",
                    evidence_object_ref_id=object_ref_id,
                    evidence_sha256=evidence.sha256,
                    idempotency_key=f"reconciliation-self-review-{suffix}",
                ),
                "trc_reconciliation_self_review",
            )
        assert getattr(self_review.value, "detail", {}).get("code") == "PUBLISH_RECONCILIATION_SECOND_PERSON_REQUIRED"

        applied = repository.review(
            tenant_id,
            submitted.case_id,
            PublicationReconciliationReviewRequest(
                action="approved",
                reviewed_by="delivery-reviewer",
                review_note="已独立读取证据对象并核对页面 URL、客户回执与内容一致。",
                evidence_object_ref_id=object_ref_id,
                evidence_sha256=evidence.sha256,
                idempotency_key=f"reconciliation-independent-review-{suffix}",
            ),
            "trc_reconciliation_independent_review",
        )
        assert applied.status == "applied"
        assert applied.external_delivery_verified is False
        assert [event.event_type for event in applied.events] == [
            "reconciliation_submitted",
            "reconciliation_approved",
            "reconciliation_applied",
        ]

        with engine.connect() as conn:
            package = conn.execute(text("SELECT status,published_url,metadata_json FROM airank_publish_packages WHERE id=:id"), {"id": package_id}).mappings().one()
            attempt = conn.execute(text("SELECT status,response_status,response_sha256,error_code,reconciliation_case_id FROM airank_publish_attempts WHERE id=:id"), {"id": attempt_id}).mappings().one()
            operation = conn.execute(text("SELECT state,response_json FROM airank_operation_guards WHERE id=:id"), {"id": claim.operation_id}).mappings().one()
            operation_events = conn.execute(text("SELECT event_sequence,event_type,previous_event_sha256,event_sha256 FROM airank_operation_guard_events WHERE operation_id=:id ORDER BY event_sequence"), {"id": claim.operation_id}).mappings().all()
        package_metadata = package["metadata_json"] if isinstance(package["metadata_json"], dict) else json.loads(package["metadata_json"])
        operation_response = operation["response_json"] if isinstance(operation["response_json"], dict) else json.loads(operation["response_json"])
        assert package["status"] == "delivered"
        assert package["published_url"] == "https://customer.example/evidence/reconciled"
        assert package_metadata["implementation_status"] == "partial"
        assert package_metadata["delivery_receipt"]["receipt_origin"] == "manual_reconciliation"
        assert package_metadata["delivery_receipt"]["external_delivery_verified"] is False
        assert attempt["status"] == "succeeded"
        assert attempt["response_status"] == 201
        assert attempt["reconciliation_case_id"] == submitted.case_id
        assert attempt["error_code"] == "PUBLISH_NETWORK_FAILED"
        assert operation["state"] == "succeeded"
        assert operation_response["receipt_origin"] == "manual_reconciliation"
        assert operation_response["external_delivery_verified"] is False
        assert [event["event_type"] for event in operation_events] == [
            "operation_claimed",
            "external_effect_started",
            "operation_reconciled_succeeded",
        ]
        assert operation_events[1]["previous_event_sha256"] == operation_events[0]["event_sha256"]
        assert operation_events[2]["previous_event_sha256"] == operation_events[1]["event_sha256"]
    finally:
        cleanup_tenant(engine, tenant_id)
        storage.delete(evidence.key)
