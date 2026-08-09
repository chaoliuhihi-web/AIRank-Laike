from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_v8_customer_packet_is_deterministic_multiformat_review_bundle() -> None:
    report = read("packages/evidence/src/airank_evidence/report.py")
    bundle = read("packages/evidence/src/airank_evidence/review_bundle.py")
    verifier = read("packages/evidence/src/airank_evidence/report_verifier.py")
    cli = read("scripts/verify_report_evidence_packet.py")
    web = read("apps/web/src/App.tsx")

    assert 'REPORT_EVIDENCE_PACKET_VERSION = "airank.report-evidence-packet.v8"' in report
    assert 'REPORT_REVIEW_BUNDLE_VERSION = "airank.report-review-bundle.v2"' in bundle
    for member in (
        "manifest/report-evidence.json",
        "report/report.html",
        "report/report.pdf",
        "report/report.docx",
        "review/scorecard.csv",
        "SHA256SUMS",
    ):
        assert member in bundle
    assert '"score_0_to_5"' in bundle
    assert '"",\n                "",\n                "",\n                "",\n                "",' in bundle
    assert "external 64-character SHA-256 anchor is required" in verifier
    assert "Internal consistency without an external hash anchor is not a digital signature" in bundle
    assert "--expected-sha256" in cli
    assert "导出客户报告包" in web
    assert "HTML、PDF、Word" in web
    assert "空白评分表" in web
