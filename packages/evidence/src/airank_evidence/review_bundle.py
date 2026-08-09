from __future__ import annotations

import csv
from hashlib import sha256
from html import escape
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable
from zipfile import ZIP_STORED, ZipFile, ZipInfo
from xml.sax.saxutils import escape as xml_escape


REPORT_REVIEW_BUNDLE_VERSION = "airank.report-review-bundle.v2"
REPORT_REVIEW_BUNDLE_MEMBERS = (
    "README.txt",
    "manifest/report-evidence.json",
    "report/report.html",
    "report/report.pdf",
    "report/report.docx",
    "review/scorecard.csv",
    "SHA256SUMS",
)
_FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    header_html = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{escape(_text(value))}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"


def render_report_html(manifest: dict[str, Any]) -> bytes:
    report = manifest.get("report", {})
    counts = manifest.get("counts", {})
    measurement = manifest.get("measurement", {})
    baseline = measurement.get("baseline_metrics", {})
    compare = measurement.get("compare_metrics", {})
    deltas = measurement.get("metric_deltas", {})
    integrity = manifest.get("evidence_integrity", {})
    attribution = manifest.get("attribution", {})
    limitations = measurement.get("known_limitations", [])
    samples = manifest.get("sample_index", [])
    source_governance = manifest.get("source_governance", {})
    source_entries = source_governance.get("entries", [])

    metric_names = (
        "valid_sample_rate",
        "mention_rate",
        "recommendation_rate",
        "top1_rate",
        "top3_rate",
        "top5_rate",
        "stability",
        "citation_recall_rate",
        "citation_support",
        "fact_accuracy",
    )
    metric_rows = [
        (name, baseline.get(name), compare.get(name), deltas.get(name))
        for name in metric_names
        if name in baseline or name in compare or name in deltas
    ]
    sample_rows = [
        (
            item.get("run_id"),
            item.get("provider"),
            item.get("collector_surface"),
            item.get("sample_index"),
            item.get("sample_status"),
            item.get("mention_class"),
            item.get("brand_rank"),
            item.get("snapshot_id"),
            str(item.get("answer_sha256") or "")[:16],
        )
        for item in samples
    ]
    source_rows = [
        (
            item.get("normalized_host"),
            item.get("classification_status"),
            (item.get("current_revision") or {}).get("authority_level"),
            (item.get("current_revision") or {}).get("usage_policy"),
            len(item.get("citation_ids", [])),
        )
        for item in source_entries
    ]
    limitation_html = (
        "<ul>" + "".join(f"<li>{escape(_text(item))}</li>" for item in limitations) + "</ul>"
        if limitations
        else "<p>本证据范围内没有额外已知限制项；这不等于形成因果保证。</p>"
    )
    title = escape(_text(report.get("title")))
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="icon" href="data:,">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; color:#172033; background:#eef2f7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; padding:28px; }}
    main {{ max-width:1120px; margin:0 auto; background:#fff; border:1px solid #dce3ec; border-radius:18px; padding:34px; box-shadow:0 18px 50px rgba(29,43,74,.08); }}
    h1 {{ margin:0 0 8px; font-size:30px; }} h2 {{ margin:30px 0 12px; font-size:20px; }}
    p,li {{ line-height:1.7; }} .muted {{ color:#64748b; }}
    .notice {{ padding:14px 16px; border-left:4px solid #d97706; background:#fffbeb; color:#7c2d12; }}
    .grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
    .stat {{ border:1px solid #e2e8f0; border-radius:12px; padding:14px; }} .stat b {{ display:block; font-size:22px; margin-top:4px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }} th,td {{ border:1px solid #dce3ec; padding:9px 10px; text-align:left; vertical-align:top; word-break:break-word; }} th {{ background:#f8fafc; }}
    code {{ font-family:"SFMono-Regular",Consolas,monospace; font-size:12px; word-break:break-all; }}
    @media (max-width:760px) {{ body {{ padding:0; }} main {{ border:0; border-radius:0; padding:20px; }} .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} table {{ display:block; overflow-x:auto; white-space:nowrap; }} }}
    @media print {{ html,body {{ background:#fff !important; }} body {{ padding:0; }} main {{ max-width:none; border:0; box-shadow:none; padding:0; }} .notice {{ break-inside:avoid; }} table {{ table-layout:fixed; font-size:9px; break-inside:auto; }} th,td {{ padding:5px 6px; overflow-wrap:anywhere; word-break:break-all; }} tr {{ break-inside:avoid; }} }}
  </style>
</head>
<body><main>
  <p class="muted">AIRank 可核验证据报告 · {escape(_text(manifest.get("schema_version")))}</p>
  <h1>{title}</h1>
  <p>报告 ID：<code>{escape(_text(report.get("report_id")))}</code> · 生成时间：{escape(_text(report.get("generated_at")))}</p>
  <div class="notice">本报告描述在冻结口径下观察到的结果。它不证明发布动作造成了变化，也不承诺任何模型将推荐某个品牌。请使用整包 SHA-256 与 AIRank 下载回执核对真实性。</div>
  <h2>证据摘要</h2>
  <div class="grid">
    <div class="stat">样本<b>{escape(_text(counts.get("samples", 0)))}</b></div>
    <div class="stat">引用<b>{escape(_text(counts.get("citations", 0)))}</b></div>
    <div class="stat">事实声明<b>{escape(_text(counts.get("fact_claims", 0)))}</b></div>
    <div class="stat">证据对象<b>{escape(_text(counts.get("evidence_objects", 0)))}</b></div>
  </div>
  <h2>完整性门禁</h2>
  {_table(("策略", "状态", "已验证", "总实体", "阻断", "Manifest SHA-256"), ((integrity.get("policy_version"), integrity.get("status"), integrity.get("verified_count"), integrity.get("entity_count"), integrity.get("blocking_finding_count"), integrity.get("manifest_sha256")),))}
  <h2>指标对比</h2>
  {_table(("指标", "基线", "复测", "变化"), metric_rows) if metric_rows else '<p>没有可交付的对比指标。</p>'}
  <h2>审慎归因</h2>
  <p><b>置信度：</b>{escape(_text(attribution.get("confidence")))}</p>
  <p>{escape(_text(attribution.get("conclusion")))}</p>
  <h2>已知限制</h2>{limitation_html}
  <h2>样本索引</h2>
  {_table(("Run", "Provider", "采集面", "序号", "状态", "提及分类", "排名", "Snapshot", "Answer hash 前缀"), sample_rows)}
  <h2>来源治理</h2>
  {_table(("Host", "分类状态", "权威度", "用途", "引用数"), source_rows) if source_rows else '<p>当前包没有可分类的 Citation host。</p>'}
  <h2>校验锚点</h2>
  <p>Packet ID：<code>{escape(_text(manifest.get("packet_id")))}</code></p>
  <p>Packet basis SHA-256：<code>{escape(_text(manifest.get("packet_basis_sha256")))}</code></p>
  <p>Report SHA-256：<code>{escape(_text(report.get("report_sha256")))}</code></p>
</main></body></html>"""
    return html.encode("utf-8")


def render_scorecard_csv(manifest: dict[str, Any]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "packet_id",
            "packet_basis_sha256",
            "dimension",
            "weight_percent",
            "required_evidence",
            "score_0_to_5",
            "reviewer",
            "reviewed_at",
            "rationale",
            "decision",
        )
    )
    dimensions = (
        ("measurement_quality", 25, "quality_gates + sample_index"),
        ("evidence_traceability", 25, "evidence_integrity + evidence_object_index"),
        ("source_governance", 15, "citation_index + source_governance"),
        ("fact_accuracy", 20, "fact_accuracy_index + final production reviews"),
        ("attribution_caution", 15, "attribution + known_limitations"),
    )
    for dimension, weight, evidence in dimensions:
        writer.writerow(
            (
                manifest.get("packet_id"),
                manifest.get("packet_basis_sha256"),
                dimension,
                weight,
                evidence,
                "",
                "",
                "",
                "",
                "",
            )
        )
    return output.getvalue().encode("utf-8-sig")


def _report_text_lines(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    report = manifest.get("report", {})
    counts = manifest.get("counts", {})
    measurement = manifest.get("measurement", {})
    baseline = measurement.get("baseline_metrics", {})
    compare = measurement.get("compare_metrics", {})
    deltas = measurement.get("metric_deltas", {})
    integrity = manifest.get("evidence_integrity", {})
    attribution = manifest.get("attribution", {})
    sources = (manifest.get("source_governance", {}) or {}).get("entries", [])
    samples = manifest.get("sample_index", [])
    lines: list[tuple[str, str]] = [
        ("title", _text(report.get("title"))),
        ("normal", f"AIRank 可核验证据报告 · {_text(manifest.get('schema_version'))}"),
        ("normal", f"报告 ID：{_text(report.get('report_id'))}"),
        ("normal", f"生成时间：{_text(report.get('generated_at'))}"),
        (
            "notice",
            "本报告仅描述冻结口径下观察到的结果，不证明发布动作造成变化，也不承诺任何模型将推荐某个品牌。",
        ),
        ("heading", "证据摘要"),
        (
            "normal",
            "样本 {samples} · 引用 {citations} · 事实声明 {facts} · 证据对象 {objects}".format(
                samples=_text(counts.get("samples", 0)),
                citations=_text(counts.get("citations", 0)),
                facts=_text(counts.get("fact_claims", 0)),
                objects=_text(counts.get("evidence_objects", 0)),
            ),
        ),
        ("heading", "完整性门禁"),
        (
            "normal",
            "策略 {policy} · 状态 {status} · 已验证 {verified}/{entities} · 阻断 {blocked}".format(
                policy=_text(integrity.get("policy_version")),
                status=_text(integrity.get("status")),
                verified=_text(integrity.get("verified_count")),
                entities=_text(integrity.get("entity_count")),
                blocked=_text(integrity.get("blocking_finding_count")),
            ),
        ),
        ("normal", f"Integrity manifest SHA-256：{_text(integrity.get('manifest_sha256'))}"),
        ("heading", "指标对比"),
    ]
    metric_names = (
        "valid_sample_rate",
        "mention_rate",
        "recommendation_rate",
        "top1_rate",
        "top3_rate",
        "top5_rate",
        "stability",
        "citation_recall_rate",
        "citation_support",
        "fact_accuracy",
    )
    metric_count = 0
    for name in metric_names:
        if name in baseline or name in compare or name in deltas:
            metric_count += 1
            lines.append(
                (
                    "normal",
                    f"{name}：基线 {_text(baseline.get(name))} · 复测 {_text(compare.get(name))} · 变化 {_text(deltas.get(name))}",
                )
            )
    if metric_count == 0:
        lines.append(("normal", "没有可交付的对比指标。"))
    lines.extend(
        [
            ("heading", "审慎归因"),
            ("normal", f"置信度：{_text(attribution.get('confidence'))}"),
            ("normal", _text(attribution.get("conclusion"))),
            ("heading", "已知限制"),
        ]
    )
    limitations = measurement.get("known_limitations", [])
    if limitations:
        lines.extend(("normal", _text(item)) for item in limitations)
    else:
        lines.append(("normal", "本证据范围内没有额外限制项；这不等于形成因果保证。"))
    lines.append(("page_heading", "样本索引"))
    for item in samples:
        lines.append(
            (
                "normal",
                "{run} · {provider} · {surface} · #{index} · {status} · {mention} · rank {rank} · {snapshot}".format(
                    run=_text(item.get("run_id")),
                    provider=_text(item.get("provider")),
                    surface=_text(item.get("collector_surface")),
                    index=_text(item.get("sample_index")),
                    status=_text(item.get("sample_status")),
                    mention=_text(item.get("mention_class")),
                    rank=_text(item.get("brand_rank")),
                    snapshot=_text(item.get("snapshot_id")),
                ),
            )
        )
    lines.append(("heading", "来源治理"))
    if sources:
        for item in sources:
            revision = item.get("current_revision") or {}
            lines.append(
                (
                    "normal",
                    "{host} · {status} · authority {authority} · usage {usage} · citations {citations}".format(
                        host=_text(item.get("normalized_host")),
                        status=_text(item.get("classification_status")),
                        authority=_text(revision.get("authority_level")),
                        usage=_text(revision.get("usage_policy")),
                        citations=len(item.get("citation_ids", [])),
                    ),
                )
            )
    else:
        lines.append(("normal", "当前包没有可分类的 Citation host。"))
    lines.extend(
        [
            ("heading", "校验锚点"),
            ("normal", f"Packet ID：{_text(manifest.get('packet_id'))}"),
            ("normal", f"Packet basis SHA-256：{_text(manifest.get('packet_basis_sha256'))}"),
            ("normal", f"Report SHA-256：{_text(report.get('report_sha256'))}"),
        ]
    )
    return lines


def render_report_pdf(manifest: dict[str, Any]) -> bytes:
    """Render printable HTML with the pinned Playwright Chromium and normalize time metadata."""

    from playwright.sync_api import sync_playwright

    html = render_report_html(manifest).decode("utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(java_script_enabled=False)
            try:
                page = context.new_page()
                page.set_content(html, wait_until="load")
                page.emulate_media(media="print")
                payload = page.pdf(
                    format="A4",
                    print_background=True,
                    prefer_css_page_size=False,
                    margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
                )
            finally:
                context.close()
        finally:
            browser.close()

    generated_at = str((manifest.get("report") or {}).get("generated_at") or "")
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        timestamp = parsed.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
    except ValueError:
        timestamp = "19800101000000"
    replacement = f"D:{timestamp}+00'00'".encode("ascii")
    normalized, count = re.subn(
        rb"D:\d{14}[+-]\d{2}'\d{2}'",
        replacement,
        payload,
    )
    if count != 2:
        raise ValueError("Chromium PDF metadata contract changed")
    return normalized


def _docx_paragraph(style: str, text: str) -> str:
    style_name = {
        "title": "Title",
        "heading": "Heading1",
        "page_heading": "Heading1",
        "notice": "Notice",
    }.get(
        style, "Normal"
    )
    page_break = '<w:pageBreakBefore/>' if style == "page_heading" else ""
    return (
        '<w:p><w:pPr><w:pStyle w:val="'
        + style_name
        + '"/>'
        + page_break
        + '</w:pPr><w:r><w:t xml:space="preserve">'
        + xml_escape(text)
        + "</w:t></w:r></w:p>"
    )


def render_report_docx(manifest: dict[str, Any]) -> bytes:
    """Render a deterministic OOXML Word document without runtime office tooling."""

    body = "".join(_docx_paragraph(style, value) for style, value in _report_text_lines(manifest))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    ).encode("utf-8")
    report = manifest.get("report", {})
    created_at = str(report.get("generated_at") or "1980-01-01T00:00:00Z")
    if created_at.endswith("+00:00"):
        created_at = created_at[:-6] + "Z"
    members = {
        "[Content_Types].xml": b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
        "_rels/.rels": b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
        "word/document.xml": document,
        "word/_rels/document.xml.rels": b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''',
        "word/styles.xml": b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="100" w:line="290" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="Microsoft YaHei"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/><w:color w:val="172033"/><w:sz w:val="21"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="0" w:after="160"/></w:pPr><w:rPr><w:b/><w:color w:val="172033"/><w:sz w:val="52"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/></w:pPr><w:rPr><w:b/><w:color w:val="1F4D78"/><w:sz w:val="28"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Notice"><w:name w:val="Notice"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="80" w:after="160"/></w:pPr><w:rPr><w:color w:val="9A3412"/><w:b/></w:rPr></w:style></w:styles>''',
        "docProps/core.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{xml_escape(_text(report.get('title')))}</dc:title>"
            '<dc:creator>AIRank</dc:creator><cp:lastModifiedBy>AIRank</cp:lastModifiedBy>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{xml_escape(created_at)}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{xml_escape(created_at)}</dcterms:modified>'
            f"<dc:identifier>{xml_escape(_text(report.get('report_id')))}</dc:identifier>"
            "</cp:coreProperties>"
        ).encode("utf-8"),
        "docProps/app.xml": b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>AIRank</Application><AppVersion>1.0</AppVersion></Properties>''',
    }
    output = io.BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_STORED, strict_timestamps=True) as archive:
        for name, payload in members.items():
            archive.writestr(_zip_info(name), payload)
    return output.getvalue()


def render_report_readme(manifest: dict[str, Any]) -> bytes:
    return (
        "AIRank customer evidence review bundle\n"
        f"bundle_version: {REPORT_REVIEW_BUNDLE_VERSION}\n"
        f"packet_id: {manifest.get('packet_id', '')}\n"
        f"packet_schema: {manifest.get('schema_version', '')}\n"
        f"packet_basis_sha256: {manifest.get('packet_basis_sha256', '')}\n\n"
        "Files:\n"
        "- manifest/report-evidence.json: canonical evidence manifest; raw answer bodies are not copied.\n"
        "- report/report.html: printable, evidence-indexed customer report.\n"
        "- report/report.pdf: deterministic A4 customer report for direct delivery.\n"
        "- report/report.docx: deterministic OOXML customer report for governed editing.\n"
        "- review/scorecard.csv: blank human review scorecard; no score is prefilled.\n"
        "- SHA256SUMS: hashes for every file above.\n\n"
        "Verification boundary:\n"
        "1. Compare the SHA-256 of this entire ZIP with the content_sha256 returned by AIRank or its download receipt.\n"
        "2. Verify SHA256SUMS and the deterministic manifest with scripts/verify_report_evidence_packet.py.\n"
        "3. Internal consistency without an external hash anchor is not a digital signature and does not prove origin.\n"
        "4. Observed changes are non-causal and do not guarantee future provider recommendations.\n"
    ).encode("utf-8")


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(filename=name, date_time=_FIXED_ZIP_TIMESTAMP)
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def build_report_review_bundle(
    manifest: dict[str, Any], manifest_bytes: bytes
) -> bytes:
    members = {
        "README.txt": render_report_readme(manifest),
        "manifest/report-evidence.json": manifest_bytes,
        "report/report.html": render_report_html(manifest),
        "report/report.pdf": render_report_pdf(manifest),
        "report/report.docx": render_report_docx(manifest),
        "review/scorecard.csv": render_scorecard_csv(manifest),
    }
    checksum_lines = [
        f"{sha256(payload).hexdigest()}  {name}"
        for name, payload in members.items()
    ]
    members["SHA256SUMS"] = ("\n".join(checksum_lines) + "\n").encode("ascii")

    output = io.BytesIO()
    with ZipFile(output, mode="w", compression=ZIP_STORED, strict_timestamps=True) as archive:
        for name in REPORT_REVIEW_BUNDLE_MEMBERS:
            archive.writestr(_zip_info(name), members[name])
    return output.getvalue()
