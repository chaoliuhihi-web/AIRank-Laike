from __future__ import annotations

import socket

from airank_crawler_lite import PAGE_AUDIT_RULES_VERSION, PageAuditService
from airank_outbound_security import (
    OutboundPolicy,
    OutboundResponse,
    SafeOutboundClient,
)


class FakeTransport:
    def __init__(self, *, status: int, content_type: str, body: bytes) -> None:
        self.status = status
        self.content_type = content_type
        self.body = body
        self.targets = []

    def send(self, target, method, *, headers, body, timeout_seconds, max_response_bytes):
        self.targets.append(target)
        return OutboundResponse(
            status=self.status,
            headers={"content-type": self.content_type},
            body=self.body,
            final_url=target.url,
            redirect_count=0,
            connected_ip=target.selected_ip,
        )


def service_for(html: str, *, status: int = 200, content_type: str = "text/html; charset=utf-8"):
    transport = FakeTransport(status=status, content_type=content_type, body=html.encode())
    resolver = lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
    ]
    client = SafeOutboundClient(
        OutboundPolicy(require_https=False, resolver=resolver),
        transport=transport,
        max_redirects=3,
    )
    return PageAuditService(client=client), transport


def test_page_audit_extracts_traceable_technical_evidence() -> None:
    html = """
    <!doctype html><html lang="zh-CN"><head>
      <title>AIRank 企业 GEO 证据平台</title>
      <meta name="description" content="AIRank 使用真实多平台回答、引用与不可变快照，帮助企业审计品牌可见度与事实准确性。">
      <link rel="canonical" href="https://airank.example/product">
      <script type="application/ld+json">{{"@context":"https://schema.org","@type":["Organization","SoftwareApplication"]}}</script>
    </head><body><main><h1>AIRank 企业 GEO 证据平台</h1>
      <p>真实采样回答与引用证据。</p><p>{}</p>
    </main></body></html>
    """.format("事实内容。" * 100)
    service, transport = service_for(html)

    result = service.audit("https://airank.example/product")

    assert result.rules_version == PAGE_AUDIT_RULES_VERSION
    assert result.evidence_grade == "server_fetch_dns_pinned"
    assert result.technical_extractability_score == 100
    assert result.content_sha256
    assert result.connected_ip == "93.184.216.34"
    assert result.h1_count == 1
    assert result.visible_text_chars >= 300
    assert result.json_ld_types == ("Organization", "SoftwareApplication")
    assert all(finding.status == "passed" for finding in result.findings)
    assert transport.targets[0].selected_ip == "93.184.216.34"


def test_page_audit_keeps_technical_score_separate_and_exposes_failures() -> None:
    service, _ = service_for(
        "<html><head><meta name='robots' content='noindex'></head><body><h1>A</h1><h1>B</h1></body></html>"
    )
    result = service.audit("https://airank.example/thin")
    failures = {finding.rule_id: finding for finding in result.findings if finding.status == "failed"}

    assert result.technical_extractability_score < 50
    assert "document.title" in failures
    assert "robots.indexable" in failures
    assert "heading.h1" in failures
    assert "content.visible_text" in failures
    assert all("recommend" not in finding.rule_id for finding in result.findings)


def test_non_html_response_never_receives_a_plausible_page_score() -> None:
    service, _ = service_for('{"ok":true}', content_type="application/json")
    result = service.audit("https://airank.example/api")
    assert result.technical_extractability_score <= 20
    assert next(item for item in result.findings if item.rule_id == "content.type.html").status == "failed"


def test_invalid_json_ld_is_preserved_as_a_finding() -> None:
    service, _ = service_for(
        "<html><head><title>Valid title</title><script type='application/ld+json'>{bad}</script></head>"
        "<body><main><h1>Title</h1><p>" + "body " * 100 + "</p></main></body></html>"
    )
    result = service.audit("https://airank.example/invalid-schema")
    finding = next(item for item in result.findings if item.rule_id == "structured_data.valid")
    assert finding.status == "failed"
    assert finding.evidence["invalid_json_ld_blocks"] == 1
