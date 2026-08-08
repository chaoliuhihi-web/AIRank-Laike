from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
from typing import Any, Mapping

from airank_outbound_security import OutboundPolicy, SafeOutboundClient


PAGE_AUDIT_RULES_VERSION = "airank.page-extractability.v1"
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class PageAuditFinding:
    rule_id: str
    severity: str
    status: str
    title: str
    description: str
    recommendation: str
    evidence: Mapping[str, Any]
    score_delta: int = 0

    def to_record(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "recommendation": self.recommendation,
            "evidence": dict(self.evidence),
            "score_delta": self.score_delta,
        }


@dataclass(frozen=True)
class PageAuditResult:
    requested_url: str
    final_url: str
    response_status: int
    content_type: str
    response_bytes: int
    content_sha256: str
    connected_ip: str
    redirect_count: int
    technical_extractability_score: int
    title: str
    meta_description: str
    canonical_url: str
    robots_directives: tuple[str, ...]
    h1_count: int
    visible_text_chars: int
    json_ld_types: tuple[str, ...]
    findings: tuple[PageAuditFinding, ...]
    rules_version: str = PAGE_AUDIT_RULES_VERSION
    evidence_grade: str = "server_fetch_dns_pinned"

    def to_record(self) -> dict[str, Any]:
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "response_status": self.response_status,
            "content_type": self.content_type,
            "response_bytes": self.response_bytes,
            "content_sha256": self.content_sha256,
            "connected_ip": self.connected_ip,
            "redirect_count": self.redirect_count,
            "technical_extractability_score": self.technical_extractability_score,
            "title": self.title,
            "meta_description": self.meta_description,
            "canonical_url": self.canonical_url,
            "robots_directives": list(self.robots_directives),
            "h1_count": self.h1_count,
            "visible_text_chars": self.visible_text_chars,
            "json_ld_types": list(self.json_ld_types),
            "findings": [finding.to_record() for finding in self.findings],
            "rules_version": self.rules_version,
            "evidence_grade": self.evidence_grade,
        }


class _DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.visible_parts: list[str] = []
        self.meta_description = ""
        self.robots = ""
        self.canonical_url = ""
        self.h1_values: list[str] = []
        self.heading_levels: list[int] = []
        self.json_ld_payloads: list[str] = []
        self.main_count = 0
        self.article_count = 0
        self.language = ""
        self._hidden_depth = 0
        self._in_title = False
        self._in_h1 = False
        self._h1_parts: list[str] = []
        self._json_ld_depth = 0
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag == "html":
            self.language = values.get("lang", "").strip()
        if tag in {"script", "style", "noscript", "template"}:
            self._hidden_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = values.get("name", "").strip().lower()
            if name == "description" and not self.meta_description:
                self.meta_description = values.get("content", "").strip()
            if name in {"robots", "googlebot", "bingbot"}:
                content = values.get("content", "").strip()
                self.robots = ",".join(part for part in (self.robots, content) if part)
        if tag == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonical_url = values.get("href", "").strip()
        if tag == "h1":
            self._in_h1 = True
            self._h1_parts = []
        if len(tag) == 2 and tag.startswith("h") and tag[1].isdigit():
            self.heading_levels.append(int(tag[1]))
        if tag == "main":
            self.main_count += 1
        if tag == "article":
            self.article_count += 1
        if tag == "script" and values.get("type", "").strip().lower() == "application/ld+json":
            self._json_ld_depth = self._hidden_depth
            self._json_ld_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == "h1" and self._in_h1:
            value = _clean(" ".join(self._h1_parts))
            self.h1_values.append(value)
            self._in_h1 = False
            self._h1_parts = []
        if tag == "script" and self._json_ld_depth:
            self.json_ld_payloads.append("".join(self._json_ld_parts).strip())
            self._json_ld_depth = 0
            self._json_ld_parts = []
        if tag in {"script", "style", "noscript", "template"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._in_h1:
            self._h1_parts.append(data)
        if self._json_ld_depth:
            self._json_ld_parts.append(data)
        if not self._hidden_depth:
            cleaned = _clean(data)
            if cleaned:
                self.visible_parts.append(cleaned)

    @property
    def title(self) -> str:
        return _clean(" ".join(self.title_parts))

    @property
    def visible_text(self) -> str:
        return _clean(" ".join(self.visible_parts))


def _clean(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _json_ld_types(payloads: list[str]) -> tuple[tuple[str, ...], int]:
    values: set[str] = set()
    invalid_count = 0

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            raw_type = value.get("@type")
            if isinstance(raw_type, str) and raw_type.strip():
                values.add(raw_type.strip())
            elif isinstance(raw_type, list):
                values.update(str(item).strip() for item in raw_type if str(item).strip())
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for payload in payloads:
        if not payload:
            continue
        try:
            visit(json.loads(payload))
        except json.JSONDecodeError:
            invalid_count += 1
    return tuple(sorted(values)), invalid_count


class PageAuditService:
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

    def audit(self, url: str) -> PageAuditResult:
        response = self.client.request(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml;q=0.9",
                "User-Agent": "AIRank-PageAudit/1.0",
            },
        )
        content_type = str(response.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        parser = _DocumentParser()
        decoded = ""
        if content_type in {"text/html", "application/xhtml+xml"}:
            decoded = response.body.decode("utf-8", errors="replace")
            parser.feed(decoded)
            parser.close()
        json_ld_types, invalid_json_ld = _json_ld_types(parser.json_ld_payloads)
        findings = self._findings(
            status=response.status,
            content_type=content_type,
            parser=parser,
            json_ld_types=json_ld_types,
            invalid_json_ld=invalid_json_ld,
        )
        score = max(0, min(100, 100 + sum(item.score_delta for item in findings)))
        robots = tuple(
            sorted(
                {
                    item.strip().lower()
                    for item in parser.robots.split(",")
                    if item.strip()
                }
            )
        )
        return PageAuditResult(
            requested_url=url,
            final_url=response.final_url,
            response_status=response.status,
            content_type=content_type,
            response_bytes=len(response.body),
            content_sha256=sha256(response.body).hexdigest(),
            connected_ip=response.connected_ip,
            redirect_count=response.redirect_count,
            technical_extractability_score=score,
            title=parser.title,
            meta_description=_clean(parser.meta_description),
            canonical_url=parser.canonical_url,
            robots_directives=robots,
            h1_count=len(parser.h1_values),
            visible_text_chars=len(parser.visible_text),
            json_ld_types=json_ld_types,
            findings=tuple(findings),
        )

    @staticmethod
    def _findings(
        *,
        status: int,
        content_type: str,
        parser: _DocumentParser,
        json_ld_types: tuple[str, ...],
        invalid_json_ld: int,
    ) -> list[PageAuditFinding]:
        findings: list[PageAuditFinding] = []

        def add(rule_id, severity, passed, title, description, recommendation, evidence, deduction):
            findings.append(
                PageAuditFinding(
                    rule_id=rule_id,
                    severity="info" if passed else severity,
                    status="passed" if passed else "failed",
                    title=title,
                    description=description,
                    recommendation="" if passed else recommendation,
                    evidence=evidence,
                    score_delta=0 if passed else -deduction,
                )
            )

        add(
            "http.status",
            "critical",
            200 <= status < 300,
            "页面 HTTP 状态可访问",
            f"服务器返回 HTTP {status}。",
            "修复公开访问状态，避免鉴权、5xx 或错误页成为模型抓取入口。",
            {"response_status": status},
            35,
        )
        add(
            "content.type.html",
            "critical",
            content_type in {"text/html", "application/xhtml+xml"},
            "响应是可解析 HTML",
            f"Content-Type 为 {content_type or 'missing'}。",
            "返回 text/html 或 application/xhtml+xml，并确保正文不依赖下载附件。",
            {"content_type": content_type or None},
            35,
        )
        title_length = len(parser.title)
        add(
            "document.title",
            "high",
            1 <= title_length <= 70,
            "页面标题明确",
            f"title 字符数为 {title_length}。",
            "提供唯一、具体且与页面事实主题一致的 title，建议不超过 70 个字符。",
            {"selector": "title", "text": parser.title[:200], "character_count": title_length},
            10,
        )
        description_length = len(_clean(parser.meta_description))
        add(
            "meta.description",
            "medium",
            30 <= description_length <= 200,
            "页面摘要可提取",
            f"meta description 字符数为 {description_length}。",
            "补充 30—200 字的事实型摘要，不堆砌关键词或无法证实的承诺。",
            {"selector": "meta[name=description]", "character_count": description_length},
            6,
        )
        directives = {part.strip().lower() for part in parser.robots.split(",") if part.strip()}
        noindex = "noindex" in directives or "none" in directives
        add(
            "robots.indexable",
            "critical",
            not noindex,
            "页面未声明 noindex",
            f"robots 指令为 {', '.join(sorted(directives)) or '未设置'}。",
            "移除公开证据页上的 noindex/none；如为私有页面则保留并不要作为 GEO 发布目标。",
            {"selector": "meta[name=robots]", "directives": sorted(directives)},
            30,
        )
        add(
            "link.canonical",
            "medium",
            bool(parser.canonical_url),
            "页面声明 canonical",
            "已找到 canonical。" if parser.canonical_url else "未找到 canonical。",
            "为公开事实页声明稳定的绝对 canonical URL。",
            {"selector": "link[rel=canonical]", "href": parser.canonical_url or None},
            5,
        )
        add(
            "heading.h1",
            "high",
            len(parser.h1_values) == 1,
            "页面只有一个主标题",
            f"检测到 {len(parser.h1_values)} 个 H1。",
            "保留一个能准确概括页面主题的 H1，其余层级使用 H2/H3。",
            {"selector": "h1", "count": len(parser.h1_values), "texts": parser.h1_values[:5]},
            9,
        )
        visible_chars = len(parser.visible_text)
        add(
            "content.visible_text",
            "high",
            visible_chars >= 300,
            "服务端 HTML 含可提取正文",
            f"不含脚本样式的可见正文约 {visible_chars} 字符。",
            "将关键事实、参数、FAQ 和来源说明输出为服务端 HTML 文本，而不是只存在于图片或客户端脚本。",
            {"visible_text_chars": visible_chars, "excerpt": parser.visible_text[:300]},
            14,
        )
        add(
            "semantic.main",
            "low",
            parser.main_count > 0 or parser.article_count > 0,
            "正文具有语义容器",
            f"main={parser.main_count}, article={parser.article_count}。",
            "使用 main/article 包裹主要内容，减少导航和页脚对抽取的干扰。",
            {"main_count": parser.main_count, "article_count": parser.article_count},
            3,
        )
        add(
            "structured_data.valid",
            "medium",
            invalid_json_ld == 0,
            "JSON-LD 可以解析",
            f"无法解析的 JSON-LD 块为 {invalid_json_ld} 个。",
            "修复 JSON-LD 语法并在发布前执行结构化数据验证。",
            {"invalid_json_ld_blocks": invalid_json_ld},
            7,
        )
        add(
            "structured_data.present",
            "low",
            bool(json_ld_types),
            "页面声明结构化实体",
            f"识别的 @type：{', '.join(json_ld_types) or '无'}。",
            "仅基于已审核事实补充 Organization、Product、Service、Article 或 FAQPage 等合适的 JSON-LD。",
            {"json_ld_types": list(json_ld_types)},
            4,
        )
        return findings
