from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_integrity_audit_is_persistent_drillable_and_report_blocking() -> None:
    migration = read(
        "apps/api/alembic/versions/20260808_0026_evidence_integrity_audits.py"
    )
    routes = read("apps/api/evidence_integrity_routes.py")
    report = read("apps/api/report_packet.py")
    packet = read("packages/evidence/src/airank_evidence/report.py")

    for token in (
        "airank_evidence_integrity_audits",
        "airank_evidence_integrity_findings",
        "manifest_sha256",
        "integrity_audit_id",
        "blocking_finding_count",
        "hash_mismatch_count",
        "size_mismatch_count",
    ):
        assert token in migration
    for entity_type in (
        "answer_snapshot",
        "evidence_snapshot",
        "citation_capture",
        "citation_segment",
        "knowledge_source_content",
        "knowledge_segment",
        "fact_revision",
        "object_ref",
        "scan_run_metrics",
        "report_derived_state",
    ):
        assert entity_type in routes
    assert 'POLICY_VERSION = "airank.evidence-integrity.v2"' in routes
    assert '"airank.retest-report-rebuild.v1"' in routes
    assert "MAX_PROJECT_ENTITIES = 10_000" in routes
    assert "source_boundary_mismatch" in routes
    assert "no_evidence_entities" in routes
    assert '"REPORT_EVIDENCE_INTEGRITY_BLOCKED"' in report
    assert "integrity_audit=integrity_manifest" in report
    assert 'REPORT_EVIDENCE_PACKET_VERSION = "airank.report-evidence-packet.v7"' in packet
    assert '"evidence_integrity"' in packet


def test_evidence_center_exposes_real_integrity_state_without_static_scores() -> None:
    api = read("apps/web/src/console/api.ts")
    page = read("apps/web/src/App.tsx")

    assert "fetchLatestEvidenceIntegrityAudit" in api
    assert "runEvidenceIntegrityAudit" in api
    assert "证据与派生指标完整性" in page
    assert "verified_count" in page
    assert "blocking_finding_count" in page
    assert "manifest_sha256" in page
    assert "旧报告 hash" in page
    assert "Math.random() * 100" not in page
