from __future__ import annotations

from airank_crawler_lite import CitationSourceCaptureService, segment_visible_text
from airank_outbound_security import OutboundResponse


class FakeClient:
    def __init__(self, response: OutboundResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, url: str, *, headers):
        self.calls.append((method, url, dict(headers)))
        return self.response


def test_capture_preserves_raw_hash_and_exact_visible_text_segments() -> None:
    body = (
        "<html><head><title>证据页</title><script>ignore()</script></head>"
        "<body><main><h1>引用研究</h1><p>第一条公开事实。</p><p>第二条公开事实。</p></main></body></html>"
    ).encode()
    service = CitationSourceCaptureService(
        client=FakeClient(
            OutboundResponse(
                status=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=body,
                final_url="https://example.com/evidence",
                redirect_count=0,
                connected_ip="93.184.216.34",
            )
        )  # type: ignore[arg-type]
    )
    result = service.capture("https://example.com/evidence")
    assert result.raw_body == body
    assert result.visible_text == "证据页 引用研究 第一条公开事实。 第二条公开事实。"
    assert "ignore" not in result.visible_text
    assert "".join(segment.segment_text for segment in result.segments) == result.visible_text
    assert result.connected_ip == "93.184.216.34"
    assert result.evidence_grade == "source_page_dns_pinned"


def test_segment_boundaries_are_exact_and_deterministic() -> None:
    value = " ".join(f"第{index}条证据。" for index in range(180))
    first = segment_visible_text(value, target_chars=240)
    second = segment_visible_text(value, target_chars=240)
    normalized = " ".join(value.split())
    assert first == second
    assert len(first) > 1
    assert "".join(item.segment_text for item in first) == normalized
    for index, segment in enumerate(first):
        assert segment.segment_index == index
        assert normalized[segment.source_start : segment.source_end] == segment.segment_text
