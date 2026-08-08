from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from airank_outbound_security import OutboundPolicy, SafeOutboundClient

from .page_audit import _DocumentParser, _clean


CITATION_CAPTURE_VERSION = "airank.citation-source-capture.v1"


@dataclass(frozen=True)
class CitationSourceSegment:
    segment_index: int
    source_start: int
    source_end: int
    segment_text: str
    segment_sha256: str


@dataclass(frozen=True)
class CitationSourceCaptureResult:
    requested_url: str
    final_url: str
    response_status: int
    content_type: str
    response_bytes: int
    content_sha256: str
    connected_ip: str
    redirect_count: int
    raw_body: bytes
    visible_text: str
    visible_text_sha256: str
    segments: tuple[CitationSourceSegment, ...]
    capture_version: str = CITATION_CAPTURE_VERSION
    evidence_grade: str = "source_page_dns_pinned"


def segment_visible_text(value: str, *, target_chars: int = 800) -> tuple[CitationSourceSegment, ...]:
    text = _clean(value)
    if not text:
        return ()
    if target_chars < 200:
        raise ValueError("citation source segment target must be at least 200 characters")
    segments: list[CitationSourceSegment] = []
    start = 0
    while start < len(text):
        hard_end = min(len(text), start + target_chars)
        end = hard_end
        if hard_end < len(text):
            lower = start + target_chars // 2
            candidates = [match.end() for match in re.finditer(r"[。！？；.!?;]\s|\s", text[lower:hard_end])]
            if candidates:
                end = lower + candidates[-1]
        segment_text = text[start:end]
        segments.append(
            CitationSourceSegment(
                segment_index=len(segments),
                source_start=start,
                source_end=end,
                segment_text=segment_text,
                segment_sha256=sha256(segment_text.encode("utf-8")).hexdigest(),
            )
        )
        start = end
    return tuple(segments)


class CitationSourceCaptureService:
    def __init__(
        self,
        *,
        client: SafeOutboundClient | None = None,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 2_000_000,
    ) -> None:
        self.client = client or SafeOutboundClient(
            OutboundPolicy(require_https=False),
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            max_redirects=3,
        )

    def capture(self, url: str) -> CitationSourceCaptureResult:
        response = self.client.request(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                "User-Agent": "AIRank-CitationEvidence/1.0",
            },
        )
        if not 200 <= response.status < 300:
            raise ValueError(f"citation source returned HTTP {response.status}")
        content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        decoded = response.body.decode("utf-8", errors="replace")
        if content_type in {"text/html", "application/xhtml+xml"}:
            parser = _DocumentParser()
            parser.feed(decoded)
            parser.close()
            visible_text = parser.visible_text
        elif content_type == "text/plain":
            visible_text = _clean(decoded)
        else:
            raise ValueError("citation source must return HTML or plain text")
        if not visible_text:
            raise ValueError("citation source contains no extractable text")
        return CitationSourceCaptureResult(
            requested_url=url,
            final_url=response.final_url,
            response_status=response.status,
            content_type=content_type,
            response_bytes=len(response.body),
            content_sha256=sha256(response.body).hexdigest(),
            connected_ip=response.connected_ip,
            redirect_count=response.redirect_count,
            raw_body=response.body,
            visible_text=visible_text,
            visible_text_sha256=sha256(visible_text.encode("utf-8")).hexdigest(),
            segments=segment_visible_text(visible_text),
        )
