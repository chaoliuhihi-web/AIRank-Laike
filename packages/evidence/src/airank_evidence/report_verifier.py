from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any
from zipfile import BadZipFile, ZipFile
import io

from .report import (
    REPORT_EVIDENCE_PACKET_VERSION,
    ReportEvidencePacketError,
    build_report_evidence_packet,
    canonical_json_bytes,
)
from .review_bundle import (
    REPORT_REVIEW_BUNDLE_MEMBERS,
    REPORT_REVIEW_BUNDLE_VERSION,
    render_report_docx,
    render_report_html,
    render_report_readme,
    render_scorecard_csv,
)


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 48 * 1024 * 1024


class ReportEvidencePacketVerificationError(ValueError):
    """An offline customer packet failed anchored deterministic verification."""


@dataclass(frozen=True)
class ReportEvidencePacketVerification:
    status: str
    packet_id: str
    schema_version: str
    archive_sha256: str
    packet_basis_sha256: str
    member_count: int

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "packet_id": self.packet_id,
            "schema_version": self.schema_version,
            "archive_sha256": self.archive_sha256,
            "packet_basis_sha256": self.packet_basis_sha256,
            "member_count": self.member_count,
        }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportEvidencePacketVerificationError(
                f"manifest contains duplicate key: {key}"
            )
        result[key] = value
    return result


def _parse_checksums(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ReportEvidencePacketVerificationError("SHA256SUMS is not ASCII") from exc
    result: dict[str, str] = {}
    for line in lines:
        if not line:
            continue
        digest, separator, name = line.partition("  ")
        if not separator or not SHA256_RE.fullmatch(digest) or not name:
            raise ReportEvidencePacketVerificationError("SHA256SUMS contains an invalid row")
        if name in result:
            raise ReportEvidencePacketVerificationError("SHA256SUMS contains a duplicate member")
        result[name] = digest
    return result


def _reject_nonstandard_number(value: str) -> None:
    raise ReportEvidencePacketVerificationError(
        f"manifest contains a non-standard number: {value}"
    )


def verify_report_evidence_packet(
    archive_bytes: bytes,
    *,
    expected_sha256: str,
) -> ReportEvidencePacketVerification:
    expected = expected_sha256.strip().lower()
    if not SHA256_RE.fullmatch(expected):
        raise ReportEvidencePacketVerificationError(
            "an external 64-character SHA-256 anchor is required"
        )
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise ReportEvidencePacketVerificationError("archive exceeds the verification size limit")
    actual_sha256 = sha256(archive_bytes).hexdigest()
    if actual_sha256 != expected:
        raise ReportEvidencePacketVerificationError(
            "archive SHA-256 does not match the external anchor"
        )

    try:
        with ZipFile(io.BytesIO(archive_bytes), mode="r") as archive:
            names = archive.namelist()
            if tuple(names) != REPORT_REVIEW_BUNDLE_MEMBERS:
                raise ReportEvidencePacketVerificationError(
                    "archive members or deterministic order are invalid"
                )
            if len(set(names)) != len(names):
                raise ReportEvidencePacketVerificationError("archive contains duplicate members")
            infos = archive.infolist()
            if any(info.file_size > MAX_MEMBER_BYTES for info in infos):
                raise ReportEvidencePacketVerificationError("archive member exceeds the size limit")
            if sum(info.file_size for info in infos) > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ReportEvidencePacketVerificationError("archive expands beyond the size limit")
            members = {name: archive.read(name) for name in names}
    except BadZipFile as exc:
        raise ReportEvidencePacketVerificationError("packet is not a valid ZIP archive") from exc

    expected_members = set(REPORT_REVIEW_BUNDLE_MEMBERS) - {"SHA256SUMS"}
    checksums = _parse_checksums(members["SHA256SUMS"])
    if set(checksums) != expected_members:
        raise ReportEvidencePacketVerificationError("SHA256SUMS coverage is incomplete")
    for name in expected_members:
        if sha256(members[name]).hexdigest() != checksums[name]:
            raise ReportEvidencePacketVerificationError(f"member hash mismatch: {name}")

    manifest_bytes = members["manifest/report-evidence.json"]
    try:
        manifest = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportEvidencePacketVerificationError("manifest is not canonical UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ReportEvidencePacketVerificationError("manifest root must be an object")
    if canonical_json_bytes(manifest) != manifest_bytes:
        raise ReportEvidencePacketVerificationError("manifest bytes are not canonical")
    if manifest.get("schema_version") != REPORT_EVIDENCE_PACKET_VERSION:
        raise ReportEvidencePacketVerificationError("packet schema is not the current verifiable version")
    if manifest.get("bundle_version") != REPORT_REVIEW_BUNDLE_VERSION:
        raise ReportEvidencePacketVerificationError("packet bundle version is unsupported")
    source_record = manifest.get("source_record")
    if not isinstance(source_record, dict):
        raise ReportEvidencePacketVerificationError("manifest source_record is missing")

    source_governance = manifest.get("source_governance")
    if not isinstance(source_governance, dict):
        raise ReportEvidencePacketVerificationError("manifest source_governance is missing")
    try:
        rebuilt = build_report_evidence_packet(
            report_record=source_record,
            sample_index=list(manifest.get("sample_index") or []),
            citation_index=list(manifest.get("citation_index") or []),
            fact_accuracy_index=list(manifest.get("fact_accuracy_index") or []),
            evidence_object_index=list(manifest.get("evidence_object_index") or []),
            source_governance={
                key: value
                for key, value in source_governance.items()
                if key not in {"summary", "known_limitations"}
            },
            integrity_audit=dict(manifest.get("evidence_integrity") or {}),
            render_bundle=False,
        )
    except (ReportEvidencePacketError, TypeError, ValueError) as exc:
        raise ReportEvidencePacketVerificationError(
            f"manifest deterministic rebuild failed: {exc}"
        ) from exc
    if rebuilt.manifest_bytes != manifest_bytes:
        raise ReportEvidencePacketVerificationError("manifest does not match deterministic rebuild")
    deterministic_members = {
        "README.txt": render_report_readme(manifest),
        "report/report.html": render_report_html(manifest),
        "report/report.docx": render_report_docx(manifest),
        "review/scorecard.csv": render_scorecard_csv(manifest),
    }
    for name, expected_payload in deterministic_members.items():
        if members[name] != expected_payload:
            raise ReportEvidencePacketVerificationError(
                f"rendered member does not match deterministic rebuild: {name}"
            )
    pdf_payload = members["report/report.pdf"]
    if (
        len(pdf_payload) < 1024
        or not pdf_payload.startswith(b"%PDF-1.4")
        or not pdf_payload.rstrip().endswith(b"%%EOF")
        or b"/JavaScript" in pdf_payload
        or b"/JS " in pdf_payload
    ):
        raise ReportEvidencePacketVerificationError("PDF report artifact is invalid or unsafe")

    return ReportEvidencePacketVerification(
        status="verified",
        packet_id=rebuilt.packet_id,
        schema_version=REPORT_EVIDENCE_PACKET_VERSION,
        archive_sha256=actual_sha256,
        packet_basis_sha256=str(manifest["packet_basis_sha256"]),
        member_count=len(REPORT_REVIEW_BUNDLE_MEMBERS),
    )
