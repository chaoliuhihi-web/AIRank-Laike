from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_customer_report_evidence_packet_has_immutable_delivery_contract() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0018_report_evidence_packets.py"
    ).read_text(encoding="utf-8")
    version_history_migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0021_versioned_report_packets.py"
    ).read_text(encoding="utf-8")
    repository = (ROOT / "apps" / "api" / "report_packet.py").read_text(encoding="utf-8")
    evidence_builder = (
        ROOT / "packages" / "evidence" / "src" / "airank_evidence" / "report.py"
    ).read_text(encoding="utf-8")
    api = (ROOT / "apps" / "api" / "main.py").read_text(encoding="utf-8")

    for required in (
        "airank_report_evidence_packets",
        "report_sha256",
        "source_record_sha256",
        "content_sha256",
        "object_ref_id",
        "idempotency_key",
        "created_by",
    ):
        assert required in migration
    assert "def downgrade()" in migration
    assert "pass" in migration
    assert "DROP INDEX uk_airank_report_packet_version" in version_history_migration
    assert "idx_airank_report_packet_version_history" in version_history_migration
    assert "raise RuntimeError" in version_history_migration

    for required in (
        "airank.report-evidence-packet.v8",
        "evidence_integrity",
        "sample_index",
        "citation_index",
        "fact_accuracy_index",
        "source_governance",
        "source_authority_unclassified",
        "source_classification_expired",
        "evidence_object_index",
        "known_limitations",
        "METRIC_FORMULAS",
        "OBSERVATIONAL_ATTRIBUTION_ONLY",
        "PROVIDER_OUTPUT_VOLATILITY",
        "not_mentioned_count",
        "provider_request_audit_id",
    ):
        assert required in evidence_builder
    assert '"answer_text"' not in evidence_builder

    assert "build_report_evidence_packet" in repository
    assert "REPORT_QUALITY_BLOCKED" in repository
    assert "REPORT_RENDERING_FAILED" in repository
    assert "REPORT_EVIDENCE_MISSING" in repository
    assert "INTEGRATION_CAPABILITY_BLOCKED" in repository
    assert "report.evidence_packet_created" in repository
    assert "REPORT_EVIDENCE_INTEGRITY_BLOCKED" in repository
    assert "review_record_sha256" in repository
    assert "revision_record_sha256" in repository
    assert "_find_latest_for_report" in repository
    assert "content-addressed" not in repository  # behavior is implemented, not claimed in a response
    assert "/evidence-packets" in api
    assert "Idempotency-Key" in api
    assert "X-AIRank-User-Id" in api


def test_report_frontend_downloads_verifies_then_records_receipt() -> None:
    client = (ROOT / "apps" / "web" / "src" / "console" / "api.ts").read_text(
        encoding="utf-8"
    )
    page = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    create_at = client.index("createReportEvidencePacket(report.report_id)")
    download_at = client.index("fetch(packet.content_url", create_at)
    digest_at = client.index('crypto.subtle.digest("SHA-256"', download_at)
    blob_at = client.index("URL.createObjectURL", digest_at)
    receipt_at = client.index("recordDownloadReceipt(packet)", blob_at)
    assert create_at < download_at < digest_at < blob_at < receipt_at
    assert "EVIDENCE_INTEGRITY_FAILED" in client
    assert "crypto.randomUUID()" in client
    assert "packet_id: packet.packet_id" in client
    assert "content_sha256: packet.content_sha256" in client
    assert "多格式客户报告包已下载" in page
    assert "canonical manifest、HTML、PDF、Word、空白评分表和 SHA256SUMS" in page
    assert "来源已具备有效权威结论" in page
    assert 'title: "下载回执已记录"' not in page
