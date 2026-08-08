from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_page_audit_schema_is_immutable_tenant_scoped_and_rule_level() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0012_page_extractability_audits.py"
    ).read_text(encoding="utf-8")

    for required in (
        "airank_page_audit_runs",
        "airank_page_audit_findings",
        "tenant_id",
        "project_id",
        "idempotency_key",
        "request_sha256",
        "content_sha256",
        "connected_ip",
        "rules_version",
        "evidence_json",
        "technical_extractability_score",
    ):
        assert required in migration


def test_page_audit_uses_async_job_and_shared_dns_pinned_outbound_client() -> None:
    routes = (ROOT / "apps" / "api" / "page_audit_routes.py").read_text(encoding="utf-8")
    worker = (ROOT / "apps" / "worker" / "airank_worker" / "page_audit.py").read_text(
        encoding="utf-8"
    )
    publisher = (ROOT / "apps" / "worker" / "airank_worker" / "publisher.py").read_text(
        encoding="utf-8"
    )
    outbound = (
        ROOT
        / "packages"
        / "outbound-security"
        / "src"
        / "airank_outbound_security"
        / "client.py"
    ).read_text(encoding="utf-8")

    assert "'page.audit'" in routes
    assert "run_next_page_audit_job" in worker
    assert "SafeOutboundClient" in publisher
    assert "selected_ip" in outbound
    assert "server_hostname=self._target.host" in outbound
    assert "key.lower() not in _SENSITIVE_HEADERS" in outbound


def test_page_audit_score_cannot_be_presented_as_brand_visibility() -> None:
    crawler = (
        ROOT
        / "packages"
        / "crawler-lite"
        / "src"
        / "airank_crawler_lite"
        / "page_audit.py"
    ).read_text(encoding="utf-8")
    app = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "technical_extractability_score" in crawler
    assert "recommendation_rate" not in crawler
    assert "技术可提取性分不等于品牌推荐率" in app
