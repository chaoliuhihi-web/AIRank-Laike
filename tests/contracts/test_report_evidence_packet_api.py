from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.api import main
from apps.api.report_packet import (
    InMemoryReportEvidencePacketRepository,
    MySQLReportEvidencePacketRepository,
    ReportEvidencePacketData,
    ReportEvidencePacketSummary,
)
from apps.api.retest_routes import MySQLRetestRepository, _comparison_data
from airank_evidence import FilesystemObjectStorage
from airank_score.quality import build_measurement_quality_report


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "packages" / "contracts"


def validate_response(payload: dict) -> None:
    schema = json.loads(
        (CONTRACT_ROOT / "report_evidence_packet_response.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


class StubPacketRepository:
    def create_packet(
        self,
        tenant_id: str,
        report_id: str,
        idempotency_key: str,
        created_by: str,
        trace_id: str,
    ) -> ReportEvidencePacketData:
        assert idempotency_key == "report-packet-report-real-v1"
        assert trace_id == "trc_packet_create"
        return packet_data(tenant_id, report_id, created_by)

    def get_latest(self, tenant_id: str, report_id: str) -> ReportEvidencePacketData:
        return packet_data(tenant_id, report_id, "user_report")


def packet_data(tenant_id: str, report_id: str, created_by: str) -> ReportEvidencePacketData:
    return ReportEvidencePacketData(
        packet_id="report_packet_" + "1" * 20,
        report_id=report_id,
        tenant_id=tenant_id,
        project_id="project_report",
        schema_version="airank.report-evidence-packet.v3",
        status="ready",
        object_ref_id="object_" + "2" * 24,
        integrity_audit_id=None,
        content_url="/api/v1/evidence-objects/object_" + "2" * 24 + "/content",
        content_type="application/json",
        byte_size=2048,
        content_sha256="3" * 64,
        report_sha256="4" * 64,
        created_by=created_by,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
        summary=ReportEvidencePacketSummary(
            sample_count=24,
            citation_count=5,
            fact_claim_count=3,
            fact_accuracy_review_count=2,
            source_host_count=4,
            source_effective_classification_count=3,
            source_authority_resolved_count=2,
            source_authority_coverage_rate=0.5,
            source_authority_summary_eligible=False,
            evidence_object_count=4,
            known_limitation_count=1,
        ),
    )


def test_report_evidence_packet_api_requires_headers_and_returns_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "REPORT_EVIDENCE_PACKET_REPOSITORY", StubPacketRepository())
    client = TestClient(main.app)

    missing_headers = client.post("/api/v1/reports/report_real/evidence-packets")
    assert missing_headers.status_code == 422

    created = client.post(
        "/api/v1/reports/report_real/evidence-packets",
        headers={
            "tenant-id": "tenant_report",
            "Idempotency-Key": "report-packet-report-real-v1",
            "X-AIRank-User-Id": "user_report",
            "X-AIRank-Trace-Id": "trc_packet_create",
        },
    )
    assert created.status_code == 201
    body = created.json()
    validate_response(body)
    assert body["data"]["created_by"] == "user_report"
    assert body["data"]["summary"]["sample_count"] == 24

    latest = client.get(
        "/api/v1/reports/report_real/evidence-packets/latest",
        headers={"tenant-id": "tenant_report", "X-AIRank-Trace-Id": "trc_packet_latest"},
    )
    assert latest.status_code == 200
    validate_response(latest.json())


def test_report_evidence_packet_uses_trusted_authenticated_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    class CapturingRepository(StubPacketRepository):
        def create_packet(
            self,
            tenant_id: str,
            report_id: str,
            idempotency_key: str,
            created_by: str,
            trace_id: str,
        ) -> ReportEvidencePacketData:
            captured.append(created_by)
            return packet_data(tenant_id, report_id, created_by)

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "required")
    monkeypatch.setenv("AIRANK_AUTH_MODE", "dev_only")
    monkeypatch.setenv("AIRANK_DEFAULT_TENANT_ID", "tenant_report_auth")
    monkeypatch.setattr(main, "REPORT_EVIDENCE_PACKET_REPOSITORY", CapturingRepository())
    main._DEV_AUTH_SESSIONS.clear()
    client = TestClient(main.app)
    token = client.post(
        "/api/v1/auth/login",
        json={"username": "trusted-reporter", "password": "local", "yudao_tenant_id": "1"},
    ).json()["data"]["access_token"]

    response = client.post(
        "/api/v1/reports/report_real/evidence-packets",
        headers={
            "tenant-id": "tenant_report_auth",
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "report-packet-report-real-v1",
            "X-AIRank-User-Id": "spoofed-reporter",
        },
    )

    assert response.status_code == 201
    assert captured == ["trusted-reporter"]
    assert response.json()["data"]["created_by"] == "trusted-reporter"


def create_packet_tables(repository: MySQLReportEvidencePacketRepository) -> None:
    statements = [
        """
        CREATE TABLE airank_projects (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), deleted_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_reports (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          report_type VARCHAR(64), title VARCHAR(255), status VARCHAR(32),
          run_id VARCHAR(64), retest_run_id VARCHAR(64), metrics_json TEXT,
          report_sha256 CHAR(64), evidence_index_json TEXT, generated_by VARCHAR(64),
          generated_at DATETIME, created_at DATETIME, deleted_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_scan_runs (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          status VARCHAR(32), metrics_json TEXT, deleted_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_scan_tasks (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          run_id VARCHAR(64), question_id VARCHAR(64), provider VARCHAR(64),
          cohort_type VARCHAR(32), prompt_version_id VARCHAR(64), sample_index INT,
          session_id VARCHAR(96), collector_surface VARCHAR(32), evidence_level VARCHAR(64),
          status VARCHAR(32), error_code VARCHAR(128)
        )
        """,
        """
        CREATE TABLE airank_answer_snapshots (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          run_id VARCHAR(64), task_id VARCHAR(64), question_id VARCHAR(64),
          sample_status VARCHAR(32), answer_text TEXT, answer_sha256 CHAR(64), raw_response_sha256 CHAR(64),
          mention_class VARCHAR(32), brand_rank INT, model_name VARCHAR(128),
          model_version VARCHAR(128), search_enabled INT, locale VARCHAR(32),
          region VARCHAR(64), external_trace_id VARCHAR(128)
        )
        """,
        """
        CREATE TABLE airank_evidence_snapshots (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          answer_snapshot_id VARCHAR(64), raw_response_json TEXT, raw_response_sha256 CHAR(64),
          request_metadata_json TEXT,
          screenshot_ref_id VARCHAR(64),
          source_panel_ref_id VARCHAR(64)
        )
        """,
        """
        CREATE TABLE airank_retest_observation_windows (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          package_id VARCHAR(64), baseline_run_id VARCHAR(64), window_label VARCHAR(16),
          compare_run_id VARCHAR(64), result_json TEXT
        )
        """,
        """
        CREATE TABLE airank_retest_runs (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          observation_window_id VARCHAR(64), baseline_run_id VARCHAR(64),
          compare_run_id VARCHAR(64), summary_json TEXT
        )
        """,
        """
        CREATE TABLE airank_provider_request_audits (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), task_id VARCHAR(64),
          answer_snapshot_id VARCHAR(64), metadata_json TEXT,
          requested_at DATETIME, created_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_source_citations (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          snapshot_id VARCHAR(64), citation_order INT, title VARCHAR(512), url VARCHAR(2048),
          host VARCHAR(255), source_type VARCHAR(64), cited_text TEXT, capture_ref_id VARCHAR(64)
        )
        """,
        """
        CREATE TABLE airank_source_classification_revisions (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          normalized_host VARCHAR(253), revision_number INT,
          source_category_l1 VARCHAR(64), source_type VARCHAR(96), ecosystem VARCHAR(160),
          classification_status VARCHAR(32), classification_method VARCHAR(32),
          classification_confidence VARCHAR(16), authority_level VARCHAR(16),
          usage_policy VARCHAR(32), risk_level VARCHAR(16), evidence_note TEXT,
          evidence_url VARCHAR(2048), source_dataset_name VARCHAR(160),
          source_dataset_version VARCHAR(64), valid_until DATETIME,
          reviewed_by VARCHAR(64), reviewed_at DATETIME,
          supersedes_revision_id VARCHAR(64), idempotency_key VARCHAR(160),
          request_sha256 CHAR(64), created_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_answer_claims (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          snapshot_id VARCHAR(64), claim_text TEXT, answer_start INT, answer_end INT,
          answer_sha256 CHAR(64), claim_sha256 CHAR(64), extraction_method VARCHAR(32),
          extractor_version VARCHAR(64), claim_kind VARCHAR(32),
          subject_entity_text VARCHAR(512), created_by VARCHAR(128), created_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_citation_source_captures (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          citation_id VARCHAR(64), status VARCHAR(32), evidence_grade VARCHAR(64),
          response_bytes BIGINT,
          content_sha256 CHAR(64), visible_text_sha256 CHAR(64),
          raw_object_ref_id VARCHAR(64), text_object_ref_id VARCHAR(64), completed_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_citation_source_segments (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          capture_id VARCHAR(64), source_start INT, source_end INT,
          segment_text TEXT, segment_sha256 CHAR(64)
        )
        """,
        """
        CREATE TABLE airank_knowledge_source_contents (
          knowledge_source_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64),
          project_id VARCHAR(64), content_text TEXT, content_sha256 CHAR(64), byte_size BIGINT
        )
        """,
        """
        CREATE TABLE airank_knowledge_segments (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          knowledge_source_id VARCHAR(64), segment_text TEXT, source_start INT,
          source_end INT, content_sha256 CHAR(64)
        )
        """,
        """
        CREATE TABLE airank_fact_revisions (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          fact_text TEXT, content_sha256 CHAR(64)
        )
        """,
        """
        CREATE TABLE airank_object_refs (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          object_type VARCHAR(64), object_uri VARCHAR(2048), content_type VARCHAR(128),
          byte_size BIGINT, sha256 VARCHAR(128), metadata_json TEXT, created_at DATETIME
        )
        """,
        """
        CREATE TABLE airank_report_evidence_packets (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          report_id VARCHAR(64), schema_version VARCHAR(64), report_sha256 CHAR(64),
          source_record_sha256 CHAR(64), object_ref_id VARCHAR(64), integrity_audit_id VARCHAR(64), content_sha256 CHAR(64),
          byte_size BIGINT, summary_json TEXT, idempotency_key VARCHAR(160),
          created_by VARCHAR(128), created_at DATETIME,
          UNIQUE (tenant_id, idempotency_key), UNIQUE (tenant_id, content_sha256)
        )
        """,
        """
        CREATE TABLE airank_evidence_integrity_audits (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          policy_version VARCHAR(64), scope VARCHAR(32), status VARCHAR(32),
          entity_count INT, verified_count INT, blocking_finding_count INT,
          unavailable_count INT, hash_mismatch_count INT, size_mismatch_count INT,
          metadata_invalid_count INT, manifest_sha256 CHAR(64), idempotency_key VARCHAR(160),
          request_sha256 CHAR(64), requested_by VARCHAR(64), trace_id VARCHAR(128),
          started_at DATETIME, completed_at DATETIME, created_at DATETIME,
          UNIQUE (tenant_id, project_id, idempotency_key)
        )
        """,
        """
        CREATE TABLE airank_evidence_integrity_findings (
          id VARCHAR(64) PRIMARY KEY, audit_id VARCHAR(64), tenant_id VARCHAR(64),
          project_id VARCHAR(64), entity_type VARCHAR(64), entity_id VARCHAR(64),
          object_type VARCHAR(64), status VARCHAR(32), blocking INT,
          expected_sha256 CHAR(64), actual_sha256 CHAR(64), expected_byte_size BIGINT,
          actual_byte_size BIGINT, details_json TEXT, created_at DATETIME,
          UNIQUE (audit_id, entity_type, entity_id)
        )
        """,
        """
        CREATE TABLE airank_audit_events (
          id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), project_id VARCHAR(64),
          event_type VARCHAR(128), entity_type VARCHAR(128), entity_id VARCHAR(64),
          trace_id VARCHAR(128), payload_json TEXT, created_at DATETIME
        )
        """,
    ]
    with repository._engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def seed_publishable_report(repository: MySQLReportEvidencePacketRepository) -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    with repository._engine.begin() as conn:
        conn.execute(
            text("INSERT INTO airank_projects VALUES ('project_report', 'tenant_report', NULL)")
        )
        for run_position, run_id in enumerate(("scan_baseline", "scan_compare"), start=1):
            conn.execute(
                text(
                    "INSERT INTO airank_scan_runs VALUES "
                    "(:run_id, 'tenant_report', 'project_report', 'completed', :metrics, NULL)"
                ),
                {"run_id": run_id, "metrics": json.dumps({"task_count": 3})},
            )
            for sample_index in range(1, 4):
                task_id = f"task_{run_position}_{sample_index}"
                snapshot_id = f"snap_{run_position}_{sample_index}"
                answer_text = f"answer {run_position}-{sample_index}"
                raw_json = json.dumps(
                    {"run": run_position, "sample": sample_index},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_scan_tasks VALUES (
                          :task_id, 'tenant_report', 'project_report', :run_id, 'question_1',
                          'qianwen', 'blind', 'prompt_v1', :sample_index, :session_id, 'api',
                          'provider_api', 'completed', NULL
                        )
                        """
                    ),
                    {
                        "task_id": task_id,
                        "run_id": run_id,
                        "sample_index": sample_index,
                        "session_id": f"session_{run_position}_{sample_index}",
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_answer_snapshots VALUES (
                          :snapshot_id, 'tenant_report', 'project_report', :run_id, :task_id,
                          'question_1', 'valid', :answer_text, :answer_sha, :raw_sha, :mention_class,
                          NULL, 'qwen3.6-plus', 'qwen3.6-plus', 1, 'zh-CN', 'CN', :trace_id
                        )
                        """
                    ),
                    {
                        "snapshot_id": snapshot_id,
                        "run_id": run_id,
                        "task_id": task_id,
                        "answer_text": answer_text,
                        "answer_sha": hashlib.sha256(answer_text.encode()).hexdigest(),
                        "raw_sha": hashlib.sha256(raw_json.encode()).hexdigest(),
                        "mention_class": (
                            "not_mentioned" if run_position == 1 else "recommended"
                        ),
                        "trace_id": f"provider_request_{run_position}_{sample_index}",
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO airank_evidence_snapshots VALUES "
                        "(:id, 'tenant_report', 'project_report', :snapshot_id, :raw_json, "
                        ":raw_sha, :request_metadata, NULL, NULL)"
                    ),
                    {
                        "id": f"evidence_{run_position}_{sample_index}",
                        "snapshot_id": snapshot_id,
                        "raw_json": raw_json,
                        "raw_sha": hashlib.sha256(raw_json.encode()).hexdigest(),
                        "request_metadata": json.dumps(
                            {"provider_request": {"surface": "api"}}, sort_keys=True
                        ),
                    },
                )
                conn.execute(
                    text(
                        "INSERT INTO airank_provider_request_audits "
                        "(id, tenant_id, task_id, answer_snapshot_id, requested_at, created_at) VALUES "
                        "(:id, 'tenant_report', :task_id, :snapshot_id, :now, :now)"
                    ),
                    {
                        "id": f"provider_audit_{run_position}_{sample_index}",
                        "task_id": task_id,
                        "snapshot_id": snapshot_id,
                        "now": now,
                    },
                )
        conn.execute(
            text(
                """
                INSERT INTO airank_source_citations VALUES (
                  'cite_1', 'tenant_report', 'project_report', 'snap_2_1', 1,
                  'Official source', 'https://example.com/source', 'example.com',
                  'web', 'supporting excerpt', NULL
                )
                """
            )
        )
        baseline = MySQLRetestRepository._load_run(
            conn, "tenant_report", "project_report", "scan_baseline"
        )
        compare = MySQLRetestRepository._load_run(
            conn, "tenant_report", "project_report", "scan_compare"
        )
        result = _comparison_data(
            window={"id": "window_real", "window_label": "T+7", "package_id": "package_real"},
            baseline_run_id="scan_baseline",
            compare_run_id="scan_compare",
            baseline_quality=build_measurement_quality_report(
                run_id="scan_baseline",
                samples=baseline.samples,
                signatures=baseline.signature,
                evidence_manifests=baseline.evidence_manifests,
                run_status=baseline.run_status,
            ),
            compare_quality=build_measurement_quality_report(
                run_id="scan_compare",
                samples=compare.samples,
                signatures=compare.signature,
                evidence_manifests=compare.evidence_manifests,
                run_status=compare.run_status,
            ),
            baseline_signature=baseline.signature,
            compare_signature=compare.signature,
            completed_at=now,
        ).model_copy(update={"retest_run_id": "retest_real", "report_id": "report_real"})
        result_json = result.model_dump(mode="json")
        conn.execute(
            text(
                "INSERT INTO airank_retest_observation_windows VALUES "
                "('window_real', 'tenant_report', 'project_report', 'package_real', "
                "'scan_baseline', 'T+7', 'scan_compare', :result_json)"
            ),
            {"result_json": json.dumps(result_json, ensure_ascii=False)},
        )
        conn.execute(
            text(
                "INSERT INTO airank_retest_runs VALUES "
                "('retest_real', 'tenant_report', 'project_report', 'window_real', "
                "'scan_baseline', 'scan_compare', :summary_json)"
            ),
            {"summary_json": json.dumps(result_json, ensure_ascii=False)},
        )
        evidence_index = {
            "package_id": "package_real",
            "window_id": "window_real",
            "baseline_run_id": "scan_baseline",
            "compare_run_id": "scan_compare",
            "evidence_refs": result.evidence_refs,
        }
        conn.execute(
            text(
                """
                INSERT INTO airank_reports (
                  id, tenant_id, project_id, report_type, title, status, run_id,
                  retest_run_id, metrics_json, report_sha256, evidence_index_json,
                  generated_by, generated_at, created_at
                ) VALUES (
                  'report_real', 'tenant_report', 'project_report', 'retest',
                  'T+7 GEO 复测观察报告', :status, 'scan_compare', 'retest_real',
                  :metrics, :report_sha256, :evidence_index, 'user_retest', :now, :now
                )
                """
            ),
            {
                "status": result.report_status,
                "metrics": json.dumps(result_json, ensure_ascii=False),
                "report_sha256": result.report_sha256,
                "evidence_index": json.dumps(evidence_index, ensure_ascii=False),
                "now": now,
            },
        )


def test_mysql_report_packet_is_content_addressed_audited_and_idempotent(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=storage,
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)

    created = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-report-real-v1",
        "user_report",
        "trc_packet_real",
    )
    replay = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-report-real-v1",
        "user_report",
        "trc_packet_replay",
    )
    latest = repository.get_latest("tenant_report", "report_real")

    assert created.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert latest.packet_id == created.packet_id
    assert created.schema_version == "airank.report-evidence-packet.v8"
    assert created.content_type == "application/zip"
    assert created.summary.sample_count == 6
    assert created.summary.citation_count == 1
    assert created.summary.source_host_count == 1
    assert created.summary.source_effective_classification_count == 0
    assert created.summary.source_authority_summary_eligible is False

    with repository._engine.connect() as conn:
        object_row = conn.execute(
            text("SELECT * FROM airank_object_refs WHERE id=:id"),
            {"id": created.object_ref_id},
        ).mappings().one()
        audits = conn.execute(
            text("SELECT * FROM airank_audit_events ORDER BY created_at, event_type")
        ).mappings().all()
    metadata = json.loads(object_row["metadata_json"])
    payload = storage.get_bytes(metadata["object_key"])
    assert hashlib.sha256(payload).hexdigest() == created.content_sha256
    with ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == [
            "README.txt",
            "manifest/report-evidence.json",
            "report/report.html",
            "report/report.pdf",
            "report/report.docx",
            "review/scorecard.csv",
            "SHA256SUMS",
        ]
        manifest = json.loads(archive.read("manifest/report-evidence.json"))
    packet_path = tmp_path / "customer-evidence-packet.zip"
    packet_path.write_bytes(payload)
    verified = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_report_evidence_packet.py"),
            str(packet_path),
            "--expected-sha256",
            created.content_sha256,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["status"] == "verified"
    assert manifest["sample_index"][0]["mention_class"] == "not_mentioned"
    assert manifest["counts"]["samples"] == 6
    assert manifest["schema_version"] == "airank.report-evidence-packet.v8"
    assert manifest["source_record"]["report_id"] == "report_real"
    assert manifest["evidence_integrity"]["status"] == "passed"
    assert created.integrity_audit_id
    assert manifest["source_governance"]["summary"]["unclassified_host_count"] == 1
    assert b"answer_text" not in payload
    assert {audit["event_type"] for audit in audits} == {
        "evidence.integrity_audited",
        "report.evidence_packet_created",
    }
    packet_audit = next(
        audit for audit in audits if audit["event_type"] == "report.evidence_packet_created"
    )
    assert packet_audit["trace_id"] == "trc_packet_real"
    assert "idempotency_key" not in packet_audit["payload_json"]


def test_mysql_report_packet_restores_missing_content_addressed_object(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=storage,
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)
    created = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-restore-v3",
        "user_report",
        "trc_packet_create",
    )
    with repository._engine.connect() as conn:
        object_row = conn.execute(
            text("SELECT metadata_json FROM airank_object_refs WHERE id=:id"),
            {"id": created.object_ref_id},
        ).mappings().one()
    object_key = json.loads(object_row["metadata_json"])["object_key"]
    storage.delete(object_key)

    restored = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-restore-v3",
        "restoring_user",
        "trc_packet_restore",
    )

    assert restored.packet_id == created.packet_id
    assert restored.content_sha256 == created.content_sha256
    assert restored.idempotent_replay is True
    assert hashlib.sha256(storage.get_bytes(object_key)).hexdigest() == created.content_sha256
    with repository._engine.connect() as conn:
        events = conn.execute(
            text("SELECT event_type, trace_id, payload_json FROM airank_audit_events ORDER BY created_at")
        ).mappings().all()
    assert [
        event["event_type"]
        for event in events
        if event["event_type"].startswith("report.")
    ] == [
        "report.evidence_packet_created",
        "report.evidence_packet_object_restored",
    ]
    restore_event = next(
        event
        for event in events
        if event["event_type"] == "report.evidence_packet_object_restored"
    )
    assert restore_event["trace_id"] == "trc_packet_restore"
    assert json.loads(restore_event["payload_json"])["restored_by"] == "restoring_user"


def test_mysql_report_packet_rejects_corrupted_existing_object(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=storage,
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)
    created = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-corrupt-v3",
        "user_report",
        "trc_packet_create",
    )
    with repository._engine.connect() as conn:
        object_row = conn.execute(
            text("SELECT metadata_json FROM airank_object_refs WHERE id=:id"),
            {"id": created.object_ref_id},
        ).mappings().one()
    object_key = json.loads(object_row["metadata_json"])["object_key"]
    target = storage._target(object_key)
    target.chmod(0o644)
    target.write_bytes(b"tampered")

    with pytest.raises(StarletteHTTPException) as exc_info:
        repository.create_packet(
            "tenant_report",
            "report_real",
            "report-packet-corrupt-v3",
            "user_report",
            "trc_packet_corrupt",
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "EVIDENCE_INTEGRITY_FAILED"


def test_mysql_report_packet_is_blocked_by_project_integrity_failure(tmp_path: Path) -> None:
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=FilesystemObjectStorage(tmp_path / "objects"),
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE airank_evidence_snapshots "
                "SET raw_response_json='tampered-provider-response' "
                "WHERE id='evidence_1_1'"
            )
        )

    with pytest.raises(StarletteHTTPException) as exc_info:
        repository.create_packet(
            "tenant_report",
            "report_real",
            "report-packet-integrity-blocked-v5",
            "user_report",
            "trc_packet_integrity_blocked",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "REPORT_EVIDENCE_INTEGRITY_BLOCKED"
    assert exc_info.value.detail["details"]["blocking_finding_count"] >= 1
    audit_id = exc_info.value.detail["details"]["integrity_audit_id"]
    with repository._engine.connect() as conn:
        finding = conn.execute(
            text(
                "SELECT entity_type, entity_id, status "
                "FROM airank_evidence_integrity_findings "
                "WHERE audit_id=:audit_id AND blocking=1"
            ),
            {"audit_id": audit_id},
        ).mappings().one()
    assert dict(finding) == {
        "entity_type": "evidence_snapshot",
        "entity_id": "evidence_1_1",
        "status": "hash_mismatch",
    }


def test_mysql_report_packet_rebuilds_derived_metrics_and_blocks_drift(tmp_path: Path) -> None:
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=FilesystemObjectStorage(tmp_path / "objects"),
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)
    with repository._engine.begin() as conn:
        report_metrics = json.loads(
            conn.execute(
                text("SELECT metrics_json FROM airank_reports WHERE id='report_real'")
            ).scalar_one()
        )
        report_metrics["conclusion"] = "tampered commercial conclusion"
        conn.execute(
            text(
                "UPDATE airank_reports SET metrics_json=:metrics, report_sha256=:sha "
                "WHERE id='report_real'"
            ),
            {"metrics": json.dumps(report_metrics), "sha": "f" * 64},
        )
        conn.execute(
            text(
                "UPDATE airank_scan_runs SET metrics_json=:metrics "
                "WHERE id='scan_baseline'"
            ),
            {"metrics": json.dumps({"task_count": 99})},
        )

    with pytest.raises(StarletteHTTPException) as exc_info:
        repository.create_packet(
            "tenant_report",
            "report_real",
            "report-packet-derived-drift-v6",
            "user_report",
            "trc_packet_derived_drift",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "REPORT_EVIDENCE_INTEGRITY_BLOCKED"
    audit_id = exc_info.value.detail["details"]["integrity_audit_id"]
    with repository._engine.connect() as conn:
        findings = conn.execute(
            text(
                "SELECT entity_type, entity_id, status FROM airank_evidence_integrity_findings "
                "WHERE audit_id=:audit_id AND blocking=1 ORDER BY entity_type"
            ),
            {"audit_id": audit_id},
        ).mappings().all()
    assert [dict(item) for item in findings] == [
        {
            "entity_type": "report_derived_state",
            "entity_id": "report_real",
            "status": "hash_mismatch",
        },
        {
            "entity_type": "scan_run_metrics",
            "entity_id": "scan_baseline",
            "status": "hash_mismatch",
        },
    ]


def test_mysql_report_packet_creates_new_immutable_version_when_source_governance_changes(
    tmp_path: Path,
) -> None:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=storage,
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)

    unclassified = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-unclassified-v3",
        "user_report",
        "trc_packet_unclassified",
    )
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_source_classification_revisions (
                  id, tenant_id, project_id, normalized_host, revision_number,
                  source_category_l1, source_type, ecosystem,
                  classification_status, classification_method,
                  classification_confidence, authority_level, usage_policy,
                  risk_level, evidence_note, evidence_url,
                  source_dataset_name, source_dataset_version, valid_until,
                  reviewed_by, reviewed_at, supersedes_revision_id,
                  idempotency_key, request_sha256, created_at
                ) VALUES (
                  'source_class_example_v1', 'tenant_report', 'project_report',
                  'example.com', 1, 'research_documentation', 'reference_documentation',
                  'Example', 'reviewed', 'human_review', 'high', 'high',
                  'primary_evidence', 'low', 'Human verified the publisher and page.',
                  'https://example.com/about', NULL, NULL, NULL,
                  'reviewer_1', '2026-08-08 12:30:00', NULL,
                  'source-review-example-v1', :request_sha256,
                  '2026-08-08 12:30:00'
                )
                """
            ),
            {"request_sha256": "d" * 64},
        )

    governed = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-governed-v3",
        "user_report",
        "trc_packet_governed",
    )
    exact_replay = repository.create_packet(
        "tenant_report",
        "report_real",
        "report-packet-governed-replay-v3",
        "user_report",
        "trc_packet_governed_replay",
    )

    assert governed.packet_id != unclassified.packet_id
    assert governed.content_sha256 != unclassified.content_sha256
    assert governed.summary.source_host_count == 1
    assert governed.summary.source_effective_classification_count == 1
    assert governed.summary.source_authority_resolved_count == 1
    assert governed.summary.source_authority_coverage_rate == 1.0
    assert governed.summary.source_authority_summary_eligible is True
    assert exact_replay.packet_id == governed.packet_id
    assert exact_replay.idempotent_replay is True
    assert repository.get_latest("tenant_report", "report_real").packet_id == governed.packet_id

    with repository._engine.connect() as conn:
        packet_count = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM airank_report_evidence_packets
                WHERE tenant_id='tenant_report' AND report_id='report_real'
                      AND schema_version='airank.report-evidence-packet.v8'
                """
            )
        ).scalar_one()
    assert packet_count == 2


def test_mysql_report_packet_rejects_idempotency_key_reuse(tmp_path: Path) -> None:
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=FilesystemObjectStorage(tmp_path / "objects"),
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)
    repository.create_packet(
        "tenant_report", "report_real", "same-idempotency-key", "user_report", "trc_1"
    )

    with pytest.raises(StarletteHTTPException) as exc_info:
        repository.create_packet(
            "tenant_report", "report_other", "same-idempotency-key", "user_report", "trc_2"
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "IDEMPOTENCY_CONFLICT"


def test_latest_packet_keeps_historical_v1_downloadable(tmp_path: Path) -> None:
    repository = MySQLReportEvidencePacketRepository(
        "sqlite+pysqlite:///:memory:",
        object_storage=FilesystemObjectStorage(tmp_path / "objects"),
    )
    create_packet_tables(repository)
    seed_publishable_report(repository)
    with repository._engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO airank_object_refs VALUES (
                  'object_111111111111111111111111', 'tenant_report', 'project_report',
                  'report_evidence_packet', 'file:///historical-v1.json', 'application/json',
                  128, :sha256, '{}', '2026-08-08 11:00:00'
                )
                """
            ),
            {"sha256": "1" * 64},
        )
        conn.execute(
            text(
                """
                INSERT INTO airank_report_evidence_packets VALUES (
                  'report_packet_11111111111111111111', 'tenant_report', 'project_report',
                  'report_real', 'airank.report-evidence-packet.v1', :report_sha256,
                      :source_sha256, 'object_111111111111111111111111', NULL, :content_sha256,
                  128, :summary_json, 'historical-v1-key', 'historical-reporter',
                  '2026-08-08 11:00:00'
                )
                """
            ),
            {
                "report_sha256": "8" * 64,
                "source_sha256": "2" * 64,
                "content_sha256": "1" * 64,
                "summary_json": json.dumps(
                    {"samples": 2, "citations": 1, "evidence_objects": 0, "known_limitations": 1}
                ),
            },
        )

    latest = repository.get_latest("tenant_report", "report_real")

    assert latest.schema_version == "airank.report-evidence-packet.v1"
    assert latest.summary.fact_claim_count == 0
    assert latest.summary.fact_accuracy_review_count == 0


def test_in_memory_report_packet_repository_fails_closed() -> None:
    repository = InMemoryReportEvidencePacketRepository()
    with pytest.raises(StarletteHTTPException) as exc_info:
        repository.create_packet("tenant", "report", "packet-key", "user", "trace")
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "INTEGRATION_CAPABILITY_BLOCKED"
