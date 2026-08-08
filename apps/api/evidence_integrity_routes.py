from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
from threading import Lock
from typing import Any, Callable, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_evidence import ObjectStorage, ObjectStorageError, build_object_storage_from_env

try:
    from .retest_routes import MySQLRetestRepository, _comparison_data
except ImportError:  # pragma: no cover - supports direct uvicorn execution.
    from retest_routes import MySQLRetestRepository, _comparison_data  # type: ignore[no-redef]


TRACE_HEADER = "X-AIRank-Trace-Id"
EVIDENCE_INTEGRITY_POLICY_VERSION = "airank.evidence-integrity.v2"
MAX_PROJECT_ENTITIES = 10_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

IntegrityStatus = Literal["passed", "blocked", "failed"]
FindingStatus = Literal[
    "verified",
    "metadata_invalid",
    "unavailable",
    "driver_mismatch",
    "hash_mismatch",
    "size_mismatch",
    "scope_too_large",
]

router = APIRouter(prefix="/api/v1", tags=["evidence-integrity"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"unsupported datetime {value!r}")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def json_value(value: object, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class EvidenceIntegrityAuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["project"] = "project"


class EvidenceIntegrityFindingData(BaseModel):
    finding_id: str
    entity_type: str
    entity_id: str
    object_type: Optional[str]
    status: FindingStatus
    blocking: bool
    expected_sha256: Optional[str]
    actual_sha256: Optional[str]
    expected_byte_size: Optional[int]
    actual_byte_size: Optional[int]
    details: dict[str, Any]
    created_at: datetime


class EvidenceIntegrityAuditData(BaseModel):
    audit_id: str
    tenant_id: str
    project_id: str
    policy_version: Literal[
        "airank.evidence-integrity.v1",
        "airank.evidence-integrity.v2",
    ]
    scope: Literal["project"]
    status: IntegrityStatus
    entity_count: int
    verified_count: int
    blocking_finding_count: int
    unavailable_count: int
    hash_mismatch_count: int
    size_mismatch_count: int
    metadata_invalid_count: int
    manifest_sha256: str
    request_sha256: str
    requested_by: str
    trace_id: str
    started_at: datetime
    completed_at: datetime
    findings: list[EvidenceIntegrityFindingData]
    idempotent_replay: bool = False


class EvidenceIntegrityAuditResponse(BaseModel):
    data: EvidenceIntegrityAuditData
    meta: dict[str, str]


class EvidenceIntegrityLatestResponse(BaseModel):
    data: Optional[EvidenceIntegrityAuditData]
    meta: dict[str, str]


class EvidenceIntegrityRepository(Protocol):
    def run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        idempotency_key: str,
        requested_by: str,
        trace_id: str,
    ) -> EvidenceIntegrityAuditData: ...

    def latest(self, tenant_id: str, project_id: str) -> Optional[EvidenceIntegrityAuditData]: ...

    def get(self, tenant_id: str, project_id: str, audit_id: str) -> EvidenceIntegrityAuditData: ...


def _finding(
    *,
    entity_type: str,
    entity_id: str,
    status: FindingStatus,
    created_at: datetime,
    object_type: Optional[str] = None,
    expected_sha256: Optional[str] = None,
    actual_sha256: Optional[str] = None,
    expected_byte_size: Optional[int] = None,
    actual_byte_size: Optional[int] = None,
    details: Optional[dict[str, Any]] = None,
) -> EvidenceIntegrityFindingData:
    return EvidenceIntegrityFindingData(
        finding_id=f"integrity_finding_{uuid4().hex[:20]}",
        entity_type=entity_type,
        entity_id=entity_id,
        object_type=object_type,
        status=status,
        blocking=status != "verified",
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        expected_byte_size=expected_byte_size,
        actual_byte_size=actual_byte_size,
        details=details or {},
        created_at=created_at,
    )


def _summary(findings: list[EvidenceIntegrityFindingData]) -> dict[str, int | str]:
    blocking = [item for item in findings if item.blocking]
    return {
        "status": "blocked" if blocking else "passed",
        "entity_count": len(findings),
        "verified_count": sum(item.status == "verified" for item in findings),
        "blocking_finding_count": len(blocking),
        "unavailable_count": sum(
            item.status in {"unavailable", "driver_mismatch"} for item in findings
        ),
        "hash_mismatch_count": sum(item.status == "hash_mismatch" for item in findings),
        "size_mismatch_count": sum(item.status == "size_mismatch" for item in findings),
        "metadata_invalid_count": sum(
            item.status in {"metadata_invalid", "scope_too_large"} for item in findings
        ),
    }


def _manifest_sha256(
    tenant_id: str,
    project_id: str,
    findings: list[EvidenceIntegrityFindingData],
) -> str:
    rows = [
        {
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "object_type": item.object_type,
            "status": item.status,
            "blocking": item.blocking,
            "expected_sha256": item.expected_sha256,
            "actual_sha256": item.actual_sha256,
            "expected_byte_size": item.expected_byte_size,
            "actual_byte_size": item.actual_byte_size,
            "details": item.details,
        }
        for item in sorted(findings, key=lambda row: (row.entity_type, row.entity_id))
    ]
    return canonical_json_sha256(
        {
            "policy_version": EVIDENCE_INTEGRITY_POLICY_VERSION,
            "scope": "project",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "findings": rows,
            "summary": _summary(findings),
        }
    )


class InMemoryEvidenceIntegrityRepository:
    def __init__(self) -> None:
        self._projects: set[tuple[str, str]] = set()
        self._audits: dict[tuple[str, str, str], EvidenceIntegrityAuditData] = {}
        self._idempotency: dict[tuple[str, str, str], str] = {}
        self._lock = Lock()

    def seed_project(self, tenant_id: str, project_id: str) -> None:
        self._projects.add((tenant_id, project_id))

    def run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        idempotency_key: str,
        requested_by: str,
        trace_id: str,
    ) -> EvidenceIntegrityAuditData:
        if (tenant_id, project_id) not in self._projects:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
            )
        request_sha256 = canonical_json_sha256(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "scope": "project",
            }
        )
        key = (tenant_id, project_id, idempotency_key)
        with self._lock:
            existing_id = self._idempotency.get(key)
            if existing_id:
                existing = self._audits[(tenant_id, project_id, existing_id)]
                if existing.request_sha256 != request_sha256:
                    raise StarletteHTTPException(
                        status_code=409,
                        detail={"code": "IDEMPOTENCY_CONFLICT", "details": {"idempotency_key": idempotency_key}},
                    )
                return existing.model_copy(update={"idempotent_replay": True})
            timestamp = utc_now()
            findings = [
                _finding(
                    entity_type="project_scope",
                    entity_id=project_id,
                    status="metadata_invalid",
                    created_at=timestamp,
                    details={"reason": "no_evidence_entities"},
                )
            ]
            summary = _summary(findings)
            audit = EvidenceIntegrityAuditData(
                audit_id=f"integrity_audit_{uuid4().hex[:20]}",
                tenant_id=tenant_id,
                project_id=project_id,
                policy_version=EVIDENCE_INTEGRITY_POLICY_VERSION,
                scope="project",
                manifest_sha256=_manifest_sha256(tenant_id, project_id, findings),
                request_sha256=request_sha256,
                requested_by=requested_by,
                trace_id=trace_id,
                started_at=timestamp,
                completed_at=timestamp,
                findings=findings,
                **summary,
            )
            self._audits[(tenant_id, project_id, audit.audit_id)] = audit
            self._idempotency[key] = audit.audit_id
            return audit

    def latest(self, tenant_id: str, project_id: str) -> Optional[EvidenceIntegrityAuditData]:
        rows = [
            audit
            for (row_tenant, row_project, _), audit in self._audits.items()
            if row_tenant == tenant_id and row_project == project_id
        ]
        return max(rows, key=lambda row: row.completed_at) if rows else None

    def get(self, tenant_id: str, project_id: str, audit_id: str) -> EvidenceIntegrityAuditData:
        audit = self._audits.get((tenant_id, project_id, audit_id))
        if audit is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "EVIDENCE_INTEGRITY_AUDIT_NOT_FOUND", "details": {"audit_id": audit_id}},
            )
        return audit


class MySQLEvidenceIntegrityRepository:
    EXPECTED_TABLES = (
        "airank_answer_snapshots",
        "airank_evidence_snapshots",
        "airank_citation_source_captures",
        "airank_citation_source_segments",
        "airank_knowledge_source_contents",
        "airank_knowledge_segments",
        "airank_fact_revisions",
        "airank_object_refs",
        "airank_scan_runs",
        "airank_scan_tasks",
        "airank_reports",
        "airank_retest_runs",
        "airank_retest_observation_windows",
    )

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
        object_storage: ObjectStorage | None = None,
        object_storage_factory: Callable[[], ObjectStorage] = build_object_storage_from_env,
        max_project_entities: int = MAX_PROJECT_ENTITIES,
    ) -> None:
        if engine is None and not database_url:
            raise ValueError("database_url or engine is required")
        self._engine = engine or create_engine(str(database_url), pool_pre_ping=True)
        self._object_storage = object_storage
        self._object_storage_factory = object_storage_factory
        self._max_project_entities = max_project_entities

    def _storage(self) -> ObjectStorage:
        if self._object_storage is None:
            self._object_storage = self._object_storage_factory()
        return self._object_storage

    def run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        idempotency_key: str,
        requested_by: str,
        trace_id: str,
    ) -> EvidenceIntegrityAuditData:
        request_sha256 = canonical_json_sha256(
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "scope": "project",
            }
        )
        started_at = utc_now()
        with self._engine.begin() as conn:
            project = conn.execute(
                text(
                    "SELECT id FROM airank_projects "
                    "WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).first()
            if project is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
                )
            existing = conn.execute(
                text(
                    "SELECT id, request_sha256 FROM airank_evidence_integrity_audits "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "AND idempotency_key=:idempotency_key"
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "idempotency_key": idempotency_key,
                },
            ).mappings().first()
            if existing is not None:
                if str(existing["request_sha256"]) != request_sha256:
                    raise StarletteHTTPException(
                        status_code=409,
                        detail={"code": "IDEMPOTENCY_CONFLICT", "details": {"idempotency_key": idempotency_key}},
                    )
                return self._load(conn, tenant_id, project_id, str(existing["id"]), replay=True)

            findings = self._verify_project(conn, tenant_id, project_id, started_at)
            if not findings:
                findings.append(
                    _finding(
                        entity_type="project_scope",
                        entity_id=project_id,
                        status="metadata_invalid",
                        created_at=started_at,
                        details={"reason": "no_evidence_entities"},
                    )
                )
            completed_at = utc_now()
            summary = _summary(findings)
            manifest_sha256 = _manifest_sha256(tenant_id, project_id, findings)
            audit_id = f"integrity_audit_{uuid4().hex[:20]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_evidence_integrity_audits (
                      id, tenant_id, project_id, policy_version, scope, status,
                      entity_count, verified_count, blocking_finding_count,
                      unavailable_count, hash_mismatch_count, size_mismatch_count,
                      metadata_invalid_count, manifest_sha256, idempotency_key,
                      request_sha256, requested_by, trace_id, started_at,
                      completed_at, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :policy_version, 'project', :status,
                      :entity_count, :verified_count, :blocking_finding_count,
                      :unavailable_count, :hash_mismatch_count, :size_mismatch_count,
                      :metadata_invalid_count, :manifest_sha256, :idempotency_key,
                      :request_sha256, :requested_by, :trace_id, :started_at,
                      :completed_at, :created_at
                    )
                    """
                ),
                {
                    "id": audit_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "policy_version": EVIDENCE_INTEGRITY_POLICY_VERSION,
                    "manifest_sha256": manifest_sha256,
                    "idempotency_key": idempotency_key,
                    "request_sha256": request_sha256,
                    "requested_by": requested_by,
                    "trace_id": trace_id,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "created_at": completed_at,
                    **summary,
                },
            )
            for item in findings:
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_evidence_integrity_findings (
                          id, audit_id, tenant_id, project_id, entity_type,
                          entity_id, object_type, status, blocking,
                          expected_sha256, actual_sha256, expected_byte_size,
                          actual_byte_size, details_json, created_at
                        ) VALUES (
                          :id, :audit_id, :tenant_id, :project_id, :entity_type,
                          :entity_id, :object_type, :status, :blocking,
                          :expected_sha256, :actual_sha256, :expected_byte_size,
                          :actual_byte_size, :details_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": item.finding_id,
                        "audit_id": audit_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "entity_type": item.entity_type,
                        "entity_id": item.entity_id,
                        "object_type": item.object_type,
                        "status": item.status,
                        "blocking": 1 if item.blocking else 0,
                        "expected_sha256": item.expected_sha256,
                        "actual_sha256": item.actual_sha256,
                        "expected_byte_size": item.expected_byte_size,
                        "actual_byte_size": item.actual_byte_size,
                        "details_json": json.dumps(item.details, ensure_ascii=False, sort_keys=True),
                        "created_at": item.created_at,
                    },
                )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, event_type, entity_type,
                      entity_id, trace_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'evidence.integrity_audited',
                      'evidence_integrity_audit', :entity_id, :trace_id,
                      :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": f"audit_{uuid4().hex[:20]}",
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "entity_id": audit_id,
                    "trace_id": trace_id,
                    "payload_json": json.dumps(
                        {
                            "policy_version": EVIDENCE_INTEGRITY_POLICY_VERSION,
                            "status": summary["status"],
                            "entity_count": summary["entity_count"],
                            "blocking_finding_count": summary["blocking_finding_count"],
                            "manifest_sha256": manifest_sha256,
                            "requested_by": requested_by,
                        },
                        sort_keys=True,
                    ),
                    "created_at": completed_at,
                },
            )
            return self._load(conn, tenant_id, project_id, audit_id, replay=False)

    def latest(self, tenant_id: str, project_id: str) -> Optional[EvidenceIntegrityAuditData]:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT id FROM airank_evidence_integrity_audits "
                    "WHERE tenant_id=:tenant_id AND project_id=:project_id "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().first()
            if row is None:
                return None
            return self._load(conn, tenant_id, project_id, str(row["id"]), replay=False)

    def get(self, tenant_id: str, project_id: str, audit_id: str) -> EvidenceIntegrityAuditData:
        with self._engine.begin() as conn:
            return self._load(conn, tenant_id, project_id, audit_id, replay=False)

    def _verify_project(
        self, conn: Any, tenant_id: str, project_id: str, timestamp: datetime
    ) -> list[EvidenceIntegrityFindingData]:
        available_tables = set(inspect(conn).get_table_names())
        missing_tables = sorted(set(self.EXPECTED_TABLES) - available_tables)
        if missing_tables:
            return [
                _finding(
                    entity_type="database_schema",
                    entity_id=table_name,
                    status="metadata_invalid",
                    created_at=timestamp,
                    details={"reason": "required_table_missing"},
                )
                for table_name in missing_tables
            ]

        params = {"tenant_id": tenant_id, "project_id": project_id}
        entity_tables = (
            "airank_object_refs",
            "airank_answer_snapshots",
            "airank_evidence_snapshots",
            "airank_citation_source_captures",
            "airank_citation_source_segments",
            "airank_knowledge_source_contents",
            "airank_knowledge_segments",
            "airank_fact_revisions",
            "airank_scan_runs",
            "airank_reports",
        )
        entity_counts = {
            table_name: int(
                conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table_name} "
                        "WHERE tenant_id=:tenant_id AND project_id=:project_id"
                        + (
                            " AND object_type <> 'report_evidence_packet'"
                            if table_name == "airank_object_refs"
                            else " AND deleted_at IS NULL"
                            if table_name in {"airank_scan_runs", "airank_reports"}
                            else ""
                        )
                    ),
                    params,
                ).scalar_one()
            )
            for table_name in entity_tables
        }
        total_entities = sum(entity_counts.values())
        if total_entities > self._max_project_entities:
            return [
                _finding(
                    entity_type="project_scope",
                    entity_id=project_id,
                    status="scope_too_large",
                    created_at=timestamp,
                    details={
                        "entity_count": total_entities,
                        "entity_counts": entity_counts,
                        "max_project_entities": self._max_project_entities,
                        "reason": "audit_requires_partitioning",
                    },
                )
            ]

        object_rows = conn.execute(
            text(
                "SELECT id, object_type, byte_size, sha256, metadata_json "
                "FROM airank_object_refs WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND object_type <> 'report_evidence_packet' "
                "ORDER BY id"
            ),
            params,
        ).mappings().all()
        answer_rows = conn.execute(
            text(
                "SELECT id, sample_status, answer_text, answer_sha256, raw_response_sha256 "
                "FROM airank_answer_snapshots WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "ORDER BY id"
            ),
            params,
        ).mappings().all()
        evidence_rows = conn.execute(
            text(
                "SELECT id, answer_snapshot_id, raw_response_json, raw_response_sha256 "
                "FROM airank_evidence_snapshots WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "ORDER BY id"
            ),
            params,
        ).mappings().all()
        capture_rows = conn.execute(
            text(
                "SELECT id, status, response_bytes, content_sha256, visible_text_sha256, "
                "raw_object_ref_id, text_object_ref_id FROM airank_citation_source_captures "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY id"
            ),
            params,
        ).mappings().all()
        citation_segment_rows = conn.execute(
            text(
                "SELECT s.id, s.capture_id, s.source_start, s.source_end, s.segment_text, "
                "s.segment_sha256, c.text_object_ref_id "
                "FROM airank_citation_source_segments s "
                "JOIN airank_citation_source_captures c ON c.tenant_id=s.tenant_id AND c.id=s.capture_id "
                "WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id ORDER BY s.id"
            ),
            params,
        ).mappings().all()
        knowledge_content_rows = conn.execute(
            text(
                "SELECT knowledge_source_id AS id, content_text, content_sha256, byte_size "
                "FROM airank_knowledge_source_contents "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY knowledge_source_id"
            ),
            params,
        ).mappings().all()
        knowledge_segment_rows = conn.execute(
            text(
                "SELECT s.id, s.knowledge_source_id, s.segment_text, s.source_start, s.source_end, "
                "s.content_sha256, c.content_text AS source_text "
                "FROM airank_knowledge_segments s "
                "JOIN airank_knowledge_source_contents c "
                "ON c.tenant_id=s.tenant_id AND c.knowledge_source_id=s.knowledge_source_id "
                "WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id ORDER BY s.id"
            ),
            params,
        ).mappings().all()
        fact_rows = conn.execute(
            text(
                "SELECT id, fact_text, content_sha256 FROM airank_fact_revisions "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY id"
            ),
            params,
        ).mappings().all()
        scan_run_rows = conn.execute(
            text(
                "SELECT r.id, r.status, r.metrics_json, COUNT(t.id) AS actual_task_count "
                "FROM airank_scan_runs r "
                "LEFT JOIN airank_scan_tasks t "
                "ON t.tenant_id=r.tenant_id AND t.project_id=r.project_id AND t.run_id=r.id "
                "WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id "
                "AND r.deleted_at IS NULL GROUP BY r.id, r.status, r.metrics_json ORDER BY r.id"
            ),
            params,
        ).mappings().all()
        report_rows = conn.execute(
            text(
                "SELECT id, report_type, status, run_id, retest_run_id, metrics_json, "
                "report_sha256, evidence_index_json, generated_at "
                "FROM airank_reports WHERE tenant_id=:tenant_id AND project_id=:project_id "
                "AND deleted_at IS NULL ORDER BY id"
            ),
            params,
        ).mappings().all()

        findings: list[EvidenceIntegrityFindingData] = []
        object_payloads: dict[str, bytes] = {}
        object_actual: dict[str, tuple[str, int]] = {}
        for row in object_rows:
            item, payload = self._verify_object(row, timestamp)
            findings.append(item)
            if payload is not None:
                object_payloads[str(row["id"])] = payload
                object_actual[str(row["id"])] = (
                    hashlib.sha256(payload).hexdigest(),
                    len(payload),
                )

        evidence_by_answer = {str(row["answer_snapshot_id"]): row for row in evidence_rows}
        for row in answer_rows:
            findings.append(self._verify_answer(row, evidence_by_answer.get(str(row["id"])), timestamp))
        for row in evidence_rows:
            findings.append(
                self._verify_text_entity(
                    entity_type="evidence_snapshot",
                    entity_id=str(row["id"]),
                    value=str(row["raw_response_json"]),
                    expected_sha256=row["raw_response_sha256"],
                    timestamp=timestamp,
                )
            )
        for row in capture_rows:
            findings.append(
                self._verify_capture(row, object_payloads, object_actual, timestamp)
            )
        for row in citation_segment_rows:
            findings.append(
                self._verify_citation_segment(row, object_payloads, timestamp)
            )
        for row in knowledge_content_rows:
            findings.append(
                self._verify_text_entity(
                    entity_type="knowledge_source_content",
                    entity_id=str(row["id"]),
                    value=str(row["content_text"]),
                    expected_sha256=row["content_sha256"],
                    expected_byte_size=int(row["byte_size"]),
                    timestamp=timestamp,
                )
            )
        for row in knowledge_segment_rows:
            findings.append(self._verify_knowledge_segment(row, timestamp))
        for row in fact_rows:
            findings.append(
                self._verify_text_entity(
                    entity_type="fact_revision",
                    entity_id=str(row["id"]),
                    value=str(row["fact_text"]),
                    expected_sha256=row["content_sha256"],
                    timestamp=timestamp,
                )
            )
        for row in scan_run_rows:
            findings.append(self._verify_scan_run_metrics(row, timestamp))
        for row in report_rows:
            findings.append(
                self._verify_report_derived_state(
                    conn,
                    tenant_id,
                    project_id,
                    row,
                    timestamp,
                )
            )
        return findings

    @staticmethod
    def _verify_scan_run_metrics(
        row: Mapping[str, Any], timestamp: datetime
    ) -> EvidenceIntegrityFindingData:
        run_id = str(row["id"])
        metrics = json_value(row["metrics_json"], {})
        stored_task_count = metrics.get("task_count") if isinstance(metrics, dict) else None
        actual_task_count = int(row["actual_task_count"])
        rebuilt_basis = {"task_count": actual_task_count}
        stored_basis = {"task_count": stored_task_count}
        rebuilt_sha = canonical_json_sha256(rebuilt_basis)
        stored_sha = canonical_json_sha256(stored_basis)
        valid_stored_count = (
            isinstance(stored_task_count, int)
            and not isinstance(stored_task_count, bool)
            and stored_task_count >= 0
        )
        status: FindingStatus = (
            "verified"
            if valid_stored_count and stored_task_count == actual_task_count
            else "hash_mismatch"
        )
        return _finding(
            entity_type="scan_run_metrics",
            entity_id=run_id,
            status=status,
            expected_sha256=rebuilt_sha,
            actual_sha256=stored_sha,
            created_at=timestamp,
            details={
                "run_status": str(row["status"]),
                "stored_task_count": stored_task_count,
                "rebuilt_task_count": actual_task_count,
                "derivation_policy": "airank.scan-run-task-count.v1",
            },
        )

    @staticmethod
    def _retest_delivery_basis(value: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "window_id",
            "window_label",
            "baseline_run_id",
            "compare_run_id",
            "comparable",
            "mismatch_reasons",
            "confidence",
            "baseline_metrics",
            "compare_metrics",
            "metric_deltas",
            "conclusion",
            "attribution_policy",
            "report_status",
            "baseline_quality",
            "compare_quality",
            "known_limitations",
            "evidence_refs",
        )
        return {key: value.get(key) for key in keys}

    def _verify_report_derived_state(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        row: Mapping[str, Any],
        timestamp: datetime,
    ) -> EvidenceIntegrityFindingData:
        report_id = str(row["id"])
        report_type = str(row["report_type"] or "")
        if report_type != "retest":
            return _finding(
                entity_type="report_derived_state",
                entity_id=report_id,
                status="metadata_invalid",
                expected_sha256=None,
                actual_sha256=(
                    str(row["report_sha256"]).lower()
                    if row.get("report_sha256")
                    else None
                ),
                created_at=timestamp,
                details={
                    "reason": "report_derivation_not_supported",
                    "report_type": report_type or None,
                    "stored_status": str(row["status"] or ""),
                },
            )

        stored_report_sha = str(row["report_sha256"] or "").lower()
        stored_metrics = json_value(row["metrics_json"], {})
        evidence_index = json_value(row["evidence_index_json"], {})
        retest_run_id = str(row["retest_run_id"] or "")
        if (
            not SHA256_RE.fullmatch(stored_report_sha)
            or not isinstance(stored_metrics, dict)
            or not isinstance(evidence_index, dict)
            or not retest_run_id
        ):
            return _finding(
                entity_type="report_derived_state",
                entity_id=report_id,
                status="metadata_invalid",
                expected_sha256=None,
                actual_sha256=stored_report_sha or None,
                created_at=timestamp,
                details={
                    "reason": "report_derivation_provenance_missing",
                    "has_metrics": isinstance(stored_metrics, dict) and bool(stored_metrics),
                    "has_evidence_index": isinstance(evidence_index, dict) and bool(evidence_index),
                    "has_retest_run_id": bool(retest_run_id),
                    "has_report_sha256": bool(SHA256_RE.fullmatch(stored_report_sha)),
                },
            )

        provenance = conn.execute(
            text(
                "SELECT rr.baseline_run_id AS rr_baseline_run_id, "
                "rr.compare_run_id AS rr_compare_run_id, rr.summary_json, "
                "rr.observation_window_id, w.id, w.window_label, w.package_id, "
                "w.baseline_run_id, w.compare_run_id, w.result_json "
                "FROM airank_retest_runs rr "
                "JOIN airank_retest_observation_windows w "
                "ON w.tenant_id=rr.tenant_id AND w.id=rr.observation_window_id "
                "WHERE rr.tenant_id=:tenant_id AND rr.project_id=:project_id AND rr.id=:retest_run_id"
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "retest_run_id": retest_run_id,
            },
        ).mappings().first()
        if provenance is None:
            return _finding(
                entity_type="report_derived_state",
                entity_id=report_id,
                status="metadata_invalid",
                expected_sha256=None,
                actual_sha256=stored_report_sha,
                created_at=timestamp,
                details={"reason": "retest_run_or_window_provenance_missing"},
            )

        baseline_run_id = str(evidence_index.get("baseline_run_id") or "")
        compare_run_id = str(evidence_index.get("compare_run_id") or "")
        provenance_ids_match = bool(
            baseline_run_id
            and compare_run_id
            and baseline_run_id == str(provenance["rr_baseline_run_id"] or "")
            and compare_run_id == str(provenance["rr_compare_run_id"] or "")
            and baseline_run_id == str(provenance["baseline_run_id"] or "")
            and compare_run_id == str(provenance["compare_run_id"] or "")
        )
        if not provenance_ids_match:
            return _finding(
                entity_type="report_derived_state",
                entity_id=report_id,
                status="metadata_invalid",
                expected_sha256=None,
                actual_sha256=stored_report_sha,
                created_at=timestamp,
                details={"reason": "retest_run_provenance_mismatch"},
            )

        try:
            baseline = MySQLRetestRepository._load_run(
                conn, tenant_id, project_id, baseline_run_id
            )
            compare = MySQLRetestRepository._load_run(
                conn, tenant_id, project_id, compare_run_id
            )
            from airank_score.quality import build_measurement_quality_report

            rebuilt = _comparison_data(
                window=dict(provenance),
                baseline_run_id=baseline_run_id,
                compare_run_id=compare_run_id,
                baseline_quality=build_measurement_quality_report(
                    run_id=baseline_run_id,
                    samples=baseline.samples,
                    signatures=baseline.signature,
                    evidence_manifests=baseline.evidence_manifests,
                    run_status=baseline.run_status,
                ),
                compare_quality=build_measurement_quality_report(
                    run_id=compare_run_id,
                    samples=compare.samples,
                    signatures=compare.signature,
                    evidence_manifests=compare.evidence_manifests,
                    run_status=compare.run_status,
                ),
                baseline_signature=baseline.signature,
                compare_signature=compare.signature,
                completed_at=as_utc(row["generated_at"]),
            )
        except StarletteHTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            return _finding(
                entity_type="report_derived_state",
                entity_id=report_id,
                status="metadata_invalid",
                expected_sha256=None,
                actual_sha256=stored_report_sha,
                created_at=timestamp,
                details={
                    "reason": "report_rebuild_source_unavailable",
                    "error_code": detail.get("code"),
                },
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return _finding(
                entity_type="report_derived_state",
                entity_id=report_id,
                status="metadata_invalid",
                expected_sha256=None,
                actual_sha256=stored_report_sha,
                created_at=timestamp,
                details={
                    "reason": "report_rebuild_failed",
                    "error_type": type(exc).__name__,
                },
            )

        rebuilt_record = rebuilt.model_dump(mode="json")
        rebuilt_basis = self._retest_delivery_basis(rebuilt_record)
        stored_basis = self._retest_delivery_basis(stored_metrics)
        rebuilt_basis_sha = canonical_json_sha256(rebuilt_basis)
        stored_basis_sha = canonical_json_sha256(stored_basis)
        window_result = json_value(provenance["result_json"], {})
        retest_summary = json_value(provenance["summary_json"], {})
        window_matches = (
            isinstance(window_result, dict)
            and canonical_json_sha256(self._retest_delivery_basis(window_result))
            == rebuilt_basis_sha
        )
        retest_summary_matches = (
            isinstance(retest_summary, dict)
            and canonical_json_sha256(self._retest_delivery_basis(retest_summary))
            == rebuilt_basis_sha
        )
        stored_metrics_match = stored_basis_sha == rebuilt_basis_sha
        report_hash_matches = stored_report_sha == rebuilt.report_sha256
        report_status_matches = str(row["status"] or "") == rebuilt.report_status
        status: FindingStatus = (
            "verified"
            if all(
                (
                    stored_metrics_match,
                    report_hash_matches,
                    report_status_matches,
                    window_matches,
                    retest_summary_matches,
                )
            )
            else "hash_mismatch"
        )
        return _finding(
            entity_type="report_derived_state",
            entity_id=report_id,
            status=status,
            expected_sha256=rebuilt.report_sha256,
            actual_sha256=stored_report_sha,
            created_at=timestamp,
            details={
                "derivation_policy": "airank.retest-report-rebuild.v1",
                "stored_metrics_match": stored_metrics_match,
                "report_hash_matches": report_hash_matches,
                "report_status_matches": report_status_matches,
                "window_result_matches": window_matches,
                "retest_summary_matches": retest_summary_matches,
                "rebuilt_basis_sha256": rebuilt_basis_sha,
                "stored_basis_sha256": stored_basis_sha,
            },
        )

    def _verify_object(
        self, row: Mapping[str, Any], timestamp: datetime
    ) -> tuple[EvidenceIntegrityFindingData, Optional[bytes]]:
        entity_id = str(row["id"])
        object_type = str(row["object_type"])
        expected_sha = str(row["sha256"] or "").lower()
        expected_size = int(row["byte_size"]) if row["byte_size"] is not None else None
        metadata = json_value(row["metadata_json"], {})
        object_key = str(metadata.get("object_key") or "") if isinstance(metadata, dict) else ""
        stored_driver = str(metadata.get("storage_driver") or "") if isinstance(metadata, dict) else ""
        if not SHA256_RE.fullmatch(expected_sha) or expected_size is None or not object_key or not stored_driver:
            return (
                _finding(
                    entity_type="object_ref",
                    entity_id=entity_id,
                    object_type=object_type,
                    status="metadata_invalid",
                    expected_sha256=expected_sha or None,
                    expected_byte_size=expected_size,
                    created_at=timestamp,
                    details={
                        "reason": "object_reference_metadata_incomplete",
                        "has_object_key": bool(object_key),
                        "has_storage_driver": bool(stored_driver),
                    },
                ),
                None,
            )
        try:
            storage = self._storage()
        except ObjectStorageError as exc:
            return (
                _finding(
                    entity_type="object_ref",
                    entity_id=entity_id,
                    object_type=object_type,
                    status="unavailable",
                    expected_sha256=expected_sha,
                    expected_byte_size=expected_size,
                    created_at=timestamp,
                    details={"reason": "storage_configuration_unavailable", "error_type": type(exc).__name__},
                ),
                None,
            )
        if storage.driver != stored_driver:
            return (
                _finding(
                    entity_type="object_ref",
                    entity_id=entity_id,
                    object_type=object_type,
                    status="driver_mismatch",
                    expected_sha256=expected_sha,
                    expected_byte_size=expected_size,
                    created_at=timestamp,
                    details={"stored_driver": stored_driver, "configured_driver": storage.driver},
                ),
                None,
            )
        try:
            payload = storage.get_bytes(object_key)
        except ObjectStorageError as exc:
            return (
                _finding(
                    entity_type="object_ref",
                    entity_id=entity_id,
                    object_type=object_type,
                    status="unavailable",
                    expected_sha256=expected_sha,
                    expected_byte_size=expected_size,
                    created_at=timestamp,
                    details={"reason": "object_read_failed", "error_type": type(exc).__name__},
                ),
                None,
            )
        actual_sha = hashlib.sha256(payload).hexdigest()
        actual_size = len(payload)
        if actual_sha != expected_sha:
            status: FindingStatus = "hash_mismatch"
        elif actual_size != expected_size:
            status = "size_mismatch"
        else:
            status = "verified"
        return (
            _finding(
                entity_type="object_ref",
                entity_id=entity_id,
                object_type=object_type,
                status=status,
                expected_sha256=expected_sha,
                actual_sha256=actual_sha,
                expected_byte_size=expected_size,
                actual_byte_size=actual_size,
                created_at=timestamp,
                details={"object_key_sha256": hashlib.sha256(object_key.encode("utf-8")).hexdigest()},
            ),
            payload,
        )

    def _verify_answer(
        self,
        row: Mapping[str, Any],
        evidence_row: Optional[Mapping[str, Any]],
        timestamp: datetime,
    ) -> EvidenceIntegrityFindingData:
        entity_id = str(row["id"])
        answer_text = str(row["answer_text"])
        expected_answer_sha = str(row["answer_sha256"] or "").lower()
        actual_answer_sha = hashlib.sha256(answer_text.encode("utf-8")).hexdigest()
        sample_status = str(row["sample_status"])
        if not expected_answer_sha:
            if sample_status != "valid" and not answer_text:
                expected_answer_sha = actual_answer_sha
            else:
                return _finding(
                    entity_type="answer_snapshot",
                    entity_id=entity_id,
                    status="metadata_invalid",
                    actual_sha256=actual_answer_sha,
                    created_at=timestamp,
                    details={"reason": "answer_hash_missing", "sample_status": sample_status},
                )
        if not SHA256_RE.fullmatch(expected_answer_sha):
            return _finding(
                entity_type="answer_snapshot",
                entity_id=entity_id,
                status="metadata_invalid",
                expected_sha256=expected_answer_sha,
                actual_sha256=actual_answer_sha,
                created_at=timestamp,
                details={"reason": "answer_hash_invalid", "sample_status": sample_status},
            )
        details: dict[str, Any] = {"sample_status": sample_status}
        status: FindingStatus = "verified" if actual_answer_sha == expected_answer_sha else "hash_mismatch"
        answer_raw_sha = str(row["raw_response_sha256"] or "").lower()
        if evidence_row is None:
            status = "metadata_invalid"
            details["reason"] = "evidence_snapshot_missing"
        else:
            evidence_raw_sha = str(evidence_row["raw_response_sha256"] or "").lower()
            if not SHA256_RE.fullmatch(answer_raw_sha) or answer_raw_sha != evidence_raw_sha:
                status = "hash_mismatch"
                details["raw_response_link"] = "mismatch"
                details["answer_raw_sha256"] = answer_raw_sha or None
                details["evidence_raw_sha256"] = evidence_raw_sha or None
        return _finding(
            entity_type="answer_snapshot",
            entity_id=entity_id,
            status=status,
            expected_sha256=expected_answer_sha,
            actual_sha256=actual_answer_sha,
            created_at=timestamp,
            details=details,
        )

    @staticmethod
    def _verify_text_entity(
        *,
        entity_type: str,
        entity_id: str,
        value: str,
        expected_sha256: object,
        timestamp: datetime,
        expected_byte_size: Optional[int] = None,
    ) -> EvidenceIntegrityFindingData:
        expected_sha = str(expected_sha256 or "").lower()
        payload = value.encode("utf-8")
        actual_sha = hashlib.sha256(payload).hexdigest()
        actual_size = len(payload)
        if not SHA256_RE.fullmatch(expected_sha):
            status: FindingStatus = "metadata_invalid"
        elif actual_sha != expected_sha:
            status = "hash_mismatch"
        elif expected_byte_size is not None and actual_size != expected_byte_size:
            status = "size_mismatch"
        else:
            status = "verified"
        return _finding(
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            expected_sha256=expected_sha or None,
            actual_sha256=actual_sha,
            expected_byte_size=expected_byte_size,
            actual_byte_size=actual_size if expected_byte_size is not None else None,
            created_at=timestamp,
            details={},
        )

    @staticmethod
    def _verify_capture(
        row: Mapping[str, Any],
        payloads: Mapping[str, bytes],
        actuals: Mapping[str, tuple[str, int]],
        timestamp: datetime,
    ) -> EvidenceIntegrityFindingData:
        entity_id = str(row["id"])
        capture_status = str(row["status"])
        raw_ref = str(row["raw_object_ref_id"] or "")
        text_ref = str(row["text_object_ref_id"] or "")
        if capture_status != "completed":
            return _finding(
                entity_type="citation_capture",
                entity_id=entity_id,
                status="verified",
                created_at=timestamp,
                details={"capture_status": capture_status, "content_integrity": "not_applicable"},
            )
        if not raw_ref or not text_ref:
            return _finding(
                entity_type="citation_capture",
                entity_id=entity_id,
                status="metadata_invalid",
                created_at=timestamp,
                details={"reason": "completed_capture_object_reference_missing"},
            )
        raw_actual = actuals.get(raw_ref)
        text_actual = actuals.get(text_ref)
        if raw_ref not in payloads or text_ref not in payloads or raw_actual is None or text_actual is None:
            return _finding(
                entity_type="citation_capture",
                entity_id=entity_id,
                status="unavailable",
                created_at=timestamp,
                details={"reason": "capture_object_unavailable", "raw_object_ref_id": raw_ref, "text_object_ref_id": text_ref},
            )
        expected_raw_sha = str(row["content_sha256"] or "").lower()
        expected_text_sha = str(row["visible_text_sha256"] or "").lower()
        expected_size = int(row["response_bytes"]) if row["response_bytes"] is not None else None
        details = {"raw_object_ref_id": raw_ref, "text_object_ref_id": text_ref}
        if not SHA256_RE.fullmatch(expected_raw_sha) or not SHA256_RE.fullmatch(expected_text_sha) or expected_size is None:
            status: FindingStatus = "metadata_invalid"
        elif expected_raw_sha != raw_actual[0] or expected_text_sha != text_actual[0]:
            status = "hash_mismatch"
            details["visible_text_sha256_matches"] = expected_text_sha == text_actual[0]
        elif expected_size != raw_actual[1]:
            status = "size_mismatch"
        else:
            status = "verified"
        return _finding(
            entity_type="citation_capture",
            entity_id=entity_id,
            status=status,
            expected_sha256=expected_raw_sha or None,
            actual_sha256=raw_actual[0],
            expected_byte_size=expected_size,
            actual_byte_size=raw_actual[1],
            created_at=timestamp,
            details=details,
        )

    @staticmethod
    def _verify_citation_segment(
        row: Mapping[str, Any], payloads: Mapping[str, bytes], timestamp: datetime
    ) -> EvidenceIntegrityFindingData:
        entity_id = str(row["id"])
        segment_text = str(row["segment_text"])
        expected_sha = str(row["segment_sha256"] or "").lower()
        actual_sha = hashlib.sha256(segment_text.encode("utf-8")).hexdigest()
        text_ref = str(row["text_object_ref_id"] or "")
        details: dict[str, Any] = {"capture_id": str(row["capture_id"]), "text_object_ref_id": text_ref or None}
        if not SHA256_RE.fullmatch(expected_sha):
            status: FindingStatus = "metadata_invalid"
        elif actual_sha != expected_sha:
            status = "hash_mismatch"
        elif not text_ref or text_ref not in payloads:
            status = "unavailable"
            details["reason"] = "captured_text_object_unavailable"
        else:
            try:
                source_text = payloads[text_ref].decode("utf-8")
            except UnicodeDecodeError:
                status = "metadata_invalid"
                details["reason"] = "captured_text_not_utf8"
            else:
                start = int(row["source_start"])
                end = int(row["source_end"])
                if start < 0 or end <= start or end > len(source_text) or source_text[start:end] != segment_text:
                    status = "hash_mismatch"
                    details["reason"] = "source_boundary_mismatch"
                    details["source_start"] = start
                    details["source_end"] = end
                    details["source_character_count"] = len(source_text)
                else:
                    status = "verified"
        return _finding(
            entity_type="citation_segment",
            entity_id=entity_id,
            status=status,
            expected_sha256=expected_sha or None,
            actual_sha256=actual_sha,
            created_at=timestamp,
            details=details,
        )

    @staticmethod
    def _verify_knowledge_segment(
        row: Mapping[str, Any], timestamp: datetime
    ) -> EvidenceIntegrityFindingData:
        entity_id = str(row["id"])
        segment_text = str(row["segment_text"])
        source_text = str(row["source_text"])
        expected_sha = str(row["content_sha256"] or "").lower()
        actual_sha = hashlib.sha256(segment_text.encode("utf-8")).hexdigest()
        start = int(row["source_start"])
        end = int(row["source_end"])
        details: dict[str, Any] = {
            "knowledge_source_id": str(row["knowledge_source_id"]),
            "source_start": start,
            "source_end": end,
            "source_character_count": len(source_text),
        }
        if not SHA256_RE.fullmatch(expected_sha):
            status: FindingStatus = "metadata_invalid"
        elif actual_sha != expected_sha:
            status = "hash_mismatch"
        elif start < 0 or end <= start or end > len(source_text) or source_text[start:end] != segment_text:
            status = "hash_mismatch"
            details["reason"] = "source_boundary_mismatch"
        else:
            status = "verified"
        return _finding(
            entity_type="knowledge_segment",
            entity_id=entity_id,
            status=status,
            expected_sha256=expected_sha or None,
            actual_sha256=actual_sha,
            created_at=timestamp,
            details=details,
        )

    def _load(
        self, conn: Any, tenant_id: str, project_id: str, audit_id: str, *, replay: bool
    ) -> EvidenceIntegrityAuditData:
        row = conn.execute(
            text(
                "SELECT * FROM airank_evidence_integrity_audits "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:audit_id"
            ),
            {"tenant_id": tenant_id, "project_id": project_id, "audit_id": audit_id},
        ).mappings().first()
        if row is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "EVIDENCE_INTEGRITY_AUDIT_NOT_FOUND", "details": {"audit_id": audit_id}},
            )
        finding_rows = conn.execute(
            text(
                "SELECT * FROM airank_evidence_integrity_findings "
                "WHERE audit_id=:audit_id ORDER BY blocking DESC, entity_type, entity_id"
            ),
            {"audit_id": audit_id},
        ).mappings().all()
        findings = [
            EvidenceIntegrityFindingData(
                finding_id=str(item["id"]),
                entity_type=str(item["entity_type"]),
                entity_id=str(item["entity_id"]),
                object_type=str(item["object_type"]) if item["object_type"] else None,
                status=str(item["status"]),
                blocking=bool(item["blocking"]),
                expected_sha256=str(item["expected_sha256"]) if item["expected_sha256"] else None,
                actual_sha256=str(item["actual_sha256"]) if item["actual_sha256"] else None,
                expected_byte_size=int(item["expected_byte_size"]) if item["expected_byte_size"] is not None else None,
                actual_byte_size=int(item["actual_byte_size"]) if item["actual_byte_size"] is not None else None,
                details=json_value(item["details_json"], {}),
                created_at=as_utc(item["created_at"]),
            )
            for item in finding_rows
        ]
        return EvidenceIntegrityAuditData(
            audit_id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            policy_version=str(row["policy_version"]),
            scope=str(row["scope"]),
            status=str(row["status"]),
            entity_count=int(row["entity_count"]),
            verified_count=int(row["verified_count"]),
            blocking_finding_count=int(row["blocking_finding_count"]),
            unavailable_count=int(row["unavailable_count"]),
            hash_mismatch_count=int(row["hash_mismatch_count"]),
            size_mismatch_count=int(row["size_mismatch_count"]),
            metadata_invalid_count=int(row["metadata_invalid_count"]),
            manifest_sha256=str(row["manifest_sha256"]),
            request_sha256=str(row["request_sha256"]),
            requested_by=str(row["requested_by"]),
            trace_id=str(row["trace_id"]),
            started_at=as_utc(row["started_at"]),
            completed_at=as_utc(row["completed_at"]),
            findings=findings,
            idempotent_replay=replay,
        )


def build_evidence_integrity_repository() -> EvidenceIntegrityRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLEvidenceIntegrityRepository(database_url)
    return InMemoryEvidenceIntegrityRepository()


EVIDENCE_INTEGRITY_REPOSITORY: EvidenceIntegrityRepository = (
    build_evidence_integrity_repository()
)


@router.post(
    "/projects/{project_id}/evidence-integrity-audits",
    response_model=EvidenceIntegrityAuditResponse,
    status_code=201,
)
def run_evidence_integrity_audit(
    project_id: str,
    payload: EvidenceIntegrityAuditRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    authenticated_actor: str = Header(alias="X-AIRank-User-Id", min_length=1, max_length=64),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> EvidenceIntegrityAuditResponse:
    del payload
    meta = response_meta(trace_id)
    return EvidenceIntegrityAuditResponse(
        data=EVIDENCE_INTEGRITY_REPOSITORY.run(
            tenant_id,
            project_id,
            idempotency_key=idempotency_key,
            requested_by=authenticated_actor,
            trace_id=meta["trace_id"],
        ),
        meta=meta,
    )


@router.get(
    "/projects/{project_id}/evidence-integrity-audits/latest",
    response_model=EvidenceIntegrityLatestResponse,
)
def get_latest_evidence_integrity_audit(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> EvidenceIntegrityLatestResponse:
    return EvidenceIntegrityLatestResponse(
        data=EVIDENCE_INTEGRITY_REPOSITORY.latest(tenant_id, project_id),
        meta=response_meta(trace_id),
    )


@router.get(
    "/projects/{project_id}/evidence-integrity-audits/{audit_id}",
    response_model=EvidenceIntegrityAuditResponse,
)
def get_evidence_integrity_audit(
    project_id: str,
    audit_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> EvidenceIntegrityAuditResponse:
    return EvidenceIntegrityAuditResponse(
        data=EVIDENCE_INTEGRITY_REPOSITORY.get(tenant_id, project_id, audit_id),
        meta=response_meta(trace_id),
    )
