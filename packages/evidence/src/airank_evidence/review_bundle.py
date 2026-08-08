from __future__ import annotations

import csv
from hashlib import sha256
from html import escape
import io
import json
from typing import Any, Iterable
from zipfile import ZIP_STORED, ZipFile, ZipInfo


REPORT_REVIEW_BUNDLE_VERSION = "airank.report-review-bundle.v1"
REPORT_REVIEW_BUNDLE_MEMBERS = (
    "README.txt",
    "manifest/report-evidence.json",
    "report/report.html",
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
    @media print {{ body {{ background:#fff; padding:0; }} main {{ max-width:none; border:0; box-shadow:none; padding:0; }} .notice {{ break-inside:avoid; }} table {{ break-inside:auto; }} tr {{ break-inside:avoid; }} }}
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


def _readme(manifest: dict[str, Any]) -> bytes:
    return (
        "AIRank customer evidence review bundle\n"
        f"bundle_version: {REPORT_REVIEW_BUNDLE_VERSION}\n"
        f"packet_id: {manifest.get('packet_id', '')}\n"
        f"packet_schema: {manifest.get('schema_version', '')}\n"
        f"packet_basis_sha256: {manifest.get('packet_basis_sha256', '')}\n\n"
        "Files:\n"
        "- manifest/report-evidence.json: canonical evidence manifest; raw answer bodies are not copied.\n"
        "- report/report.html: printable, evidence-indexed customer report.\n"
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
        "README.txt": _readme(manifest),
        "manifest/report-evidence.json": manifest_bytes,
        "report/report.html": render_report_html(manifest),
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
