from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Callable, Literal, Optional, Protocol
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_evidence import (
    ObjectStorage,
    ObjectStorageError,
    REPORT_EVIDENCE_PACKET_VERSION,
    SOURCE_GOVERNANCE_VERSION,
    ReportEvidencePacketError,
    build_object_storage_from_env,
    build_report_evidence_packet,
    canonical_json_sha256,
    normalize_source_host,
)

try:
    from .evidence_integrity_routes import (
        EvidenceIntegrityRepository,
        MySQLEvidenceIntegrityRepository,
    )
except ImportError:  # pragma: no cover - supports direct uvicorn execution.
    from evidence_integrity_routes import (  # type: ignore[no-redef]
        EvidenceIntegrityRepository,
        MySQLEvidenceIntegrityRepository,
    )


class ReportEvidencePacketSummary(BaseModel):
    sample_count: int
    citation_count: int
    fact_claim_count: int
    fact_accuracy_review_count: int
    source_host_count: int
    source_effective_classification_count: int
    source_authority_resolved_count: int
    source_authority_coverage_rate: Optional[float]
    source_authority_summary_eligible: bool
    evidence_object_count: int
    known_limitation_count: int


class ReportEvidencePacketData(BaseModel):
    packet_id: str
    report_id: str
    tenant_id: str
    project_id: str
    schema_version: Literal[
        "airank.report-evidence-packet.v1",
        "airank.report-evidence-packet.v2",
        "airank.report-evidence-packet.v3",
        "airank.report-evidence-packet.v4",
        "airank.report-evidence-packet.v5",
    ]
    status: Literal["ready"]
    object_ref_id: str
    integrity_audit_id: Optional[str]
    content_url: str
    content_type: Literal["application/json"]
    byte_size: int
    content_sha256: str
    report_sha256: str
    created_by: str
    created_at: datetime
    summary: ReportEvidencePacketSummary
    idempotent_replay: bool = False


class ReportEvidencePacketResponse(BaseModel):
    data: ReportEvidencePacketData
    meta: dict[str, str]


class ReportEvidencePacketRepository(Protocol):
    def create_packet(
        self,
        tenant_id: str,
        report_id: str,
        idempotency_key: str,
        created_by: str,
        trace_id: str,
    ) -> ReportEvidencePacketData: ...

    def get_latest(self, tenant_id: str, report_id: str) -> ReportEvidencePacketData: ...


class InMemoryReportEvidencePacketRepository:
    """Evidence packets require durable database and object storage capabilities."""

    @staticmethod
    def _blocked() -> None:
        raise StarletteHTTPException(
            status_code=503,
            detail={
                "code": "INTEGRATION_CAPABILITY_BLOCKED",
                "details": {"capability": "report_evidence_packet", "repository": "empty"},
            },
        )

    def create_packet(
        self,
        _tenant_id: str,
        _report_id: str,
        _idempotency_key: str,
        _created_by: str,
        _trace_id: str,
    ) -> ReportEvidencePacketData:
        self._blocked()
        raise AssertionError("unreachable")

    def get_latest(self, _tenant_id: str, _report_id: str) -> ReportEvidencePacketData:
        self._blocked()
        raise AssertionError("unreachable")


class MySQLReportEvidencePacketRepository:
    def __init__(
        self,
        database_url: str,
        *,
        object_storage: ObjectStorage | None = None,
        object_storage_factory: Callable[[], ObjectStorage] = build_object_storage_from_env,
        integrity_repository: EvidenceIntegrityRepository | None = None,
    ) -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._object_storage = object_storage
        self._object_storage_factory = object_storage_factory
        self._integrity_repository = integrity_repository

    def _storage(self) -> ObjectStorage:
        if self._object_storage is None:
            self._object_storage = self._object_storage_factory()
        return self._object_storage

    def _integrity(self) -> EvidenceIntegrityRepository:
        if self._integrity_repository is None:
            self._integrity_repository = MySQLEvidenceIntegrityRepository(
                engine=self._engine,
                object_storage=self._storage(),
            )
        return self._integrity_repository

    def create_packet(
        self,
        tenant_id: str,
        report_id: str,
        idempotency_key: str,
        created_by: str,
        trace_id: str,
    ) -> ReportEvidencePacketData:
        created_at = datetime.now(timezone.utc)
        unavailable_idempotent_replay = None
        with self._engine.begin() as conn:
            by_key = self._find_by_idempotency_key(conn, tenant_id, idempotency_key)
            if by_key is not None:
                if by_key["report_id"] != report_id:
                    raise StarletteHTTPException(
                        status_code=409,
                        detail={
                            "code": "IDEMPOTENCY_CONFLICT",
                            "details": {"idempotency_key": idempotency_key},
                        },
                    )
                object_status = self._packet_object_status(by_key)
                if object_status == "available":
                    return self._packet_data(by_key, replay=True)
                if object_status == "integrity_failed":
                    self._raise_object_integrity_failed(by_key)
                unavailable_idempotent_replay = by_key
            report_row = self._load_report(conn, tenant_id, report_id)
            report_record = self._report_record(report_row)
            (
                sample_index,
                citation_index,
                fact_accuracy_index,
                object_index,
                source_governance,
            ) = self._load_evidence_indices(
                conn,
                tenant_id,
                report_row["project_id"],
                report_record["evidence_index"],
                evaluated_at=_datetime_value(report_record["generated_at"]),
                evaluation_clock=created_at,
            )

        integrity_key = "report-integrity:" + hashlib.sha256(
            f"{tenant_id}:{report_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()
        integrity_audit = self._integrity().run(
            tenant_id,
            str(report_row["project_id"]),
            idempotency_key=integrity_key,
            requested_by=created_by,
            trace_id=trace_id,
        )
        if integrity_audit.status != "passed":
            raise StarletteHTTPException(
                status_code=409,
                detail={
                    "code": "REPORT_EVIDENCE_INTEGRITY_BLOCKED",
                    "details": {
                        "report_id": report_id,
                        "integrity_audit_id": integrity_audit.audit_id,
                        "blocking_finding_count": integrity_audit.blocking_finding_count,
                        "manifest_sha256": integrity_audit.manifest_sha256,
                    },
                },
            )
        integrity_manifest = {
            "policy_version": integrity_audit.policy_version,
            "status": integrity_audit.status,
            "entity_count": integrity_audit.entity_count,
            "verified_count": integrity_audit.verified_count,
            "blocking_finding_count": integrity_audit.blocking_finding_count,
            "manifest_sha256": integrity_audit.manifest_sha256,
        }

        try:
            packet = build_report_evidence_packet(
                report_record=report_record,
                sample_index=sample_index,
                citation_index=citation_index,
                fact_accuracy_index=fact_accuracy_index,
                evidence_object_index=object_index,
                source_governance=source_governance,
                integrity_audit=integrity_manifest,
            )
        except ReportEvidencePacketError as exc:
            message = str(exc)
            quality_failure = any(
                marker in message
                for marker in ("not generated", "quality contract", "not publishable")
            )
            raise StarletteHTTPException(
                status_code=409 if quality_failure else 500,
                detail={
                    "code": "REPORT_QUALITY_BLOCKED" if quality_failure else "REPORT_EVIDENCE_MISSING",
                    "details": {"report_id": report_id, "reason": message},
                },
            ) from exc

        if (
            unavailable_idempotent_replay is not None
            and str(unavailable_idempotent_replay["content_sha256"]) != packet.sha256
        ):
            self._raise_object_unavailable(
                unavailable_idempotent_replay,
                reason="idempotent_packet_missing_and_evidence_changed",
            )

        with self._engine.begin() as conn:
            exact_replay = self._find_by_content(
                conn,
                tenant_id,
                report_id,
                packet.sha256,
            )
        if exact_replay is not None:
            object_status = self._packet_object_status(exact_replay)
            if object_status == "available":
                return self._packet_data(exact_replay, replay=True)
            if object_status == "integrity_failed":
                self._raise_object_integrity_failed(exact_replay)
            if object_status == "driver_mismatch":
                self._raise_object_unavailable(
                    exact_replay,
                    reason="configured_storage_driver_mismatch",
                )
            return self._restore_packet_object(
                exact_replay,
                packet=packet,
                created_by=created_by,
                trace_id=trace_id,
                restored_at=created_at,
            )

        partition = hashlib.sha256(f"{tenant_id}:{report_row['project_id']}".encode("utf-8")).hexdigest()[:24]
        object_key = (
            f"reports/{partition}/{report_id}/{packet.sha256[:2]}/{packet.sha256}.json"
        )
        try:
            stored = self._storage().put_bytes(
                packet.canonical_bytes,
                key=object_key,
                content_type="application/json",
            )
        except ObjectStorageError as exc:
            raise StarletteHTTPException(
                status_code=503,
                detail={
                    "code": "INTEGRATION_CAPABILITY_BLOCKED",
                    "details": {
                        "capability": "report_evidence_packet_object_storage",
                        "error_type": type(exc).__name__,
                    },
                },
            ) from exc

        object_ref_id = f"object_{packet.sha256[:24]}"
        with self._engine.begin() as conn:
            replay = self._find_by_content(
                conn,
                tenant_id,
                report_id,
                packet.sha256,
            )
            if replay is not None:
                return self._packet_data(replay, replay=True)
            current_report = self._report_record(self._load_report(conn, tenant_id, report_id))
            if current_report != report_record:
                raise StarletteHTTPException(
                    status_code=409,
                    detail={
                        "code": "STATE_CONFLICT",
                        "details": {"report_id": report_id, "reason": "report_changed_during_packet_build"},
                    },
                )
            self._insert_object_ref(
                conn,
                object_ref_id=object_ref_id,
                tenant_id=tenant_id,
                project_id=report_row["project_id"],
                stored=stored,
                packet_id=packet.packet_id,
                created_at=created_at,
            )
            insert_prefix = (
                "INSERT OR IGNORE" if self._engine.dialect.name == "sqlite" else "INSERT IGNORE"
            )
            insert_result = conn.execute(
                text(
                    f"""
                    {insert_prefix} INTO airank_report_evidence_packets (
                      id, tenant_id, project_id, report_id, schema_version,
                      report_sha256, source_record_sha256, object_ref_id,
                      integrity_audit_id, content_sha256, byte_size, summary_json, idempotency_key,
                      created_by, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :report_id, :schema_version,
                      :report_sha256, :source_record_sha256, :object_ref_id,
                      :integrity_audit_id, :content_sha256, :byte_size, :summary_json, :idempotency_key,
                      :created_by, :created_at
                    )
                    """
                ),
                {
                    "id": packet.packet_id,
                    "tenant_id": tenant_id,
                    "project_id": report_row["project_id"],
                    "report_id": report_id,
                    "schema_version": REPORT_EVIDENCE_PACKET_VERSION,
                    "report_sha256": report_record["report_sha256"],
                    "source_record_sha256": packet.manifest["report"]["source_record_sha256"],
                    "object_ref_id": object_ref_id,
                    "integrity_audit_id": integrity_audit.audit_id,
                    "content_sha256": packet.sha256,
                    "byte_size": stored.byte_size,
                    "summary_json": json.dumps(packet.manifest["counts"], sort_keys=True),
                    "idempotency_key": idempotency_key,
                    "created_by": created_by,
                    "created_at": created_at,
                },
            )
            if insert_result.rowcount == 0:
                by_key = self._find_by_idempotency_key(conn, tenant_id, idempotency_key)
                if by_key is not None and by_key["report_id"] != report_id:
                    raise StarletteHTTPException(
                        status_code=409,
                        detail={
                            "code": "IDEMPOTENCY_CONFLICT",
                            "details": {"idempotency_key": idempotency_key},
                        },
                    )
                replay = self._find_by_content(
                    conn,
                    tenant_id,
                    report_id,
                    packet.sha256,
                )
                if replay is not None:
                    return self._packet_data(replay, replay=True)
                raise StarletteHTTPException(
                    status_code=409,
                    detail={
                        "code": "STATE_CONFLICT",
                        "details": {"report_id": report_id, "reason": "packet_insert_conflict"},
                    },
                )
            audit_id = f"audit_{uuid4().hex[:20]}"
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, event_type, entity_type,
                      entity_id, trace_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, 'report.evidence_packet_created',
                      'report_evidence_packet', :entity_id, :trace_id, :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": audit_id,
                    "tenant_id": tenant_id,
                    "project_id": report_row["project_id"],
                    "entity_id": packet.packet_id,
                    "trace_id": trace_id,
                    "payload_json": json.dumps(
                        {
                            "report_id": report_id,
                            "packet_id": packet.packet_id,
                            "content_sha256": packet.sha256,
                            "object_ref_id": object_ref_id,
                            "integrity_audit_id": integrity_audit.audit_id,
                            "created_by": created_by,
                        },
                        sort_keys=True,
                    ),
                    "created_at": created_at,
                },
            )
            row = self._find_by_content(
                conn,
                tenant_id,
                report_id,
                packet.sha256,
            )
            assert row is not None
            return self._packet_data(row, replay=False)

    def get_latest(self, tenant_id: str, report_id: str) -> ReportEvidencePacketData:
        with self._engine.begin() as conn:
            self._load_report(conn, tenant_id, report_id)
            row = self._find_latest_for_report(conn, tenant_id, report_id)
        if row is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={
                    "code": "REPORT_EVIDENCE_PACKET_NOT_FOUND",
                    "details": {"report_id": report_id},
                },
            )
        return self._packet_data(row, replay=False)

    def _load_report(self, conn: Any, tenant_id: str, report_id: str) -> Any:
        row = conn.execute(
            text(
                """
                SELECT id, tenant_id, project_id, report_type, title, status,
                       run_id, retest_run_id, metrics_json, report_sha256,
                       evidence_index_json, generated_by, generated_at, created_at
                FROM airank_reports
                WHERE tenant_id=:tenant_id AND id=:report_id AND deleted_at IS NULL
                """
            ),
            {"tenant_id": tenant_id, "report_id": report_id},
        ).mappings().first()
        if row is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "REPORT_NOT_FOUND", "details": {"report_id": report_id}},
            )
        return row

    def _report_record(self, row: Any) -> dict[str, Any]:
        return {
            "report_id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "project_id": str(row["project_id"]),
            "report_type": str(row["report_type"]),
            "title": str(row["title"]),
            "status": str(row["status"]),
            "run_id": str(row["run_id"]) if row["run_id"] else None,
            "retest_run_id": str(row["retest_run_id"]) if row["retest_run_id"] else None,
            "metrics": _json_value(row["metrics_json"], {}),
            "report_sha256": str(row["report_sha256"] or ""),
            "evidence_index": _json_value(row["evidence_index_json"], {}),
            "generated_by": str(row["generated_by"]) if row["generated_by"] else None,
            "generated_at": _iso_value(row["generated_at"] or row["created_at"]),
        }

    def _load_evidence_indices(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        evidence_index: Any,
        *,
        evaluated_at: datetime | None = None,
        evaluation_clock: datetime | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[str, Any],
    ]:
        if not isinstance(evidence_index, dict):
            return [], [], [], [], self._empty_source_governance(evaluated_at)
        baseline_run_id = str(evidence_index.get("baseline_run_id") or "")
        compare_run_id = str(evidence_index.get("compare_run_id") or "")
        if not baseline_run_id or not compare_run_id:
            return [], [], [], [], self._empty_source_governance(evaluated_at)
        params = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "baseline_run_id": baseline_run_id,
            "compare_run_id": compare_run_id,
        }
        sample_rows = conn.execute(
            text(
                """
                SELECT t.id AS task_id, t.run_id, t.question_id, t.provider,
                       t.cohort_type, t.prompt_version_id, t.sample_index,
                       t.session_id, t.collector_surface, t.evidence_level,
                       t.status AS task_status, t.error_code,
                       s.id AS snapshot_id, s.sample_status, s.answer_sha256,
                       s.raw_response_sha256, s.mention_class, s.brand_rank,
                       s.model_name, s.model_version, s.search_enabled,
                       s.locale, s.region, s.external_trace_id,
                       e.id AS evidence_snapshot_id, e.screenshot_ref_id,
                       e.source_panel_ref_id,
                       (SELECT a.id FROM airank_provider_request_audits a
                        WHERE a.tenant_id=t.tenant_id AND a.task_id=t.id
                        ORDER BY a.requested_at ASC, a.id ASC LIMIT 1) AS provider_request_audit_id
                FROM airank_scan_tasks t
                LEFT JOIN airank_answer_snapshots s
                  ON s.tenant_id=t.tenant_id AND s.task_id=t.id
                LEFT JOIN airank_evidence_snapshots e
                  ON e.tenant_id=s.tenant_id AND e.answer_snapshot_id=s.id
                WHERE t.tenant_id=:tenant_id AND t.project_id=:project_id
                  AND t.run_id IN (:baseline_run_id, :compare_run_id)
                ORDER BY t.run_id, t.question_id, t.provider,
                         t.collector_surface, t.sample_index, t.id
                """
            ),
            params,
        ).mappings().all()
        samples = [
            {
                "task_id": str(row["task_id"]),
                "run_id": str(row["run_id"]),
                "question_id": str(row["question_id"]),
                "provider": str(row["provider"]),
                "cohort_type": str(row["cohort_type"]),
                "prompt_version_id": str(row["prompt_version_id"]),
                "sample_index": int(row["sample_index"]),
                "session_id": str(row["session_id"]),
                "collector_surface": str(row["collector_surface"]),
                "evidence_level": str(row["evidence_level"]),
                "task_status": str(row["task_status"]),
                "error_code": str(row["error_code"]) if row["error_code"] else None,
                "snapshot_id": str(row["snapshot_id"]) if row["snapshot_id"] else None,
                "sample_status": str(row["sample_status"]) if row["sample_status"] else None,
                "answer_sha256": str(row["answer_sha256"]) if row["answer_sha256"] else None,
                "raw_response_sha256": (
                    str(row["raw_response_sha256"]) if row["raw_response_sha256"] else None
                ),
                "mention_class": str(row["mention_class"]) if row["mention_class"] else None,
                "brand_rank": int(row["brand_rank"]) if row["brand_rank"] is not None else None,
                "model_name": str(row["model_name"]) if row["model_name"] else None,
                "model_version": str(row["model_version"]) if row["model_version"] else None,
                "search_enabled": (
                    bool(row["search_enabled"]) if row["search_enabled"] is not None else None
                ),
                "locale": str(row["locale"]) if row["locale"] else None,
                "region": str(row["region"]) if row["region"] else None,
                "external_trace_id": (
                    str(row["external_trace_id"]) if row["external_trace_id"] else None
                ),
                "evidence_snapshot_id": (
                    str(row["evidence_snapshot_id"]) if row["evidence_snapshot_id"] else None
                ),
                "provider_request_audit_id": (
                    str(row["provider_request_audit_id"])
                    if row["provider_request_audit_id"]
                    else None
                ),
                "screenshot_object_ref_id": (
                    str(row["screenshot_ref_id"]) if row["screenshot_ref_id"] else None
                ),
                "source_panel_object_ref_id": (
                    str(row["source_panel_ref_id"]) if row["source_panel_ref_id"] else None
                ),
            }
            for row in sample_rows
        ]

        citation_rows = conn.execute(
            text(
                """
                SELECT c.id AS citation_id, c.snapshot_id, c.citation_order,
                       c.title, c.url, c.host, c.source_type, c.cited_text,
                       c.capture_ref_id
                FROM airank_source_citations c
                JOIN airank_answer_snapshots s
                  ON s.tenant_id=c.tenant_id AND s.id=c.snapshot_id
                WHERE c.tenant_id=:tenant_id AND c.project_id=:project_id
                  AND s.run_id IN (:baseline_run_id, :compare_run_id)
                ORDER BY s.run_id, c.snapshot_id, c.citation_order, c.id
                """
            ),
            params,
        ).mappings().all()
        capture_rows = conn.execute(
            text(
                """
                SELECT cap.id AS capture_id, cap.citation_id, cap.status,
                       cap.evidence_grade, cap.content_sha256,
                       cap.visible_text_sha256, cap.raw_object_ref_id,
                       cap.text_object_ref_id, cap.completed_at
                FROM airank_citation_source_captures cap
                JOIN airank_source_citations c
                  ON c.tenant_id=cap.tenant_id AND c.id=cap.citation_id
                JOIN airank_answer_snapshots s
                  ON s.tenant_id=c.tenant_id AND s.id=c.snapshot_id
                WHERE cap.tenant_id=:tenant_id AND cap.project_id=:project_id
                  AND s.run_id IN (:baseline_run_id, :compare_run_id)
                ORDER BY cap.citation_id, cap.completed_at, cap.id
                """
            ),
            params,
        ).mappings().all()
        captures_by_citation: dict[str, list[dict[str, Any]]] = {}
        for row in capture_rows:
            captures_by_citation.setdefault(str(row["citation_id"]), []).append(
                {
                    "capture_id": str(row["capture_id"]),
                    "status": str(row["status"]),
                    "evidence_grade": str(row["evidence_grade"]) if row["evidence_grade"] else None,
                    "content_sha256": str(row["content_sha256"]) if row["content_sha256"] else None,
                    "visible_text_sha256": (
                        str(row["visible_text_sha256"]) if row["visible_text_sha256"] else None
                    ),
                    "raw_object_ref_id": (
                        str(row["raw_object_ref_id"]) if row["raw_object_ref_id"] else None
                    ),
                    "text_object_ref_id": (
                        str(row["text_object_ref_id"]) if row["text_object_ref_id"] else None
                    ),
                    "completed_at": _iso_value(row["completed_at"]),
                }
            )
        citations = [
            {
                "citation_id": str(row["citation_id"]),
                "snapshot_id": str(row["snapshot_id"]),
                "citation_order": int(row["citation_order"]),
                "title": str(row["title"]) if row["title"] else None,
                "url": str(row["url"]) if row["url"] else None,
                "host": str(row["host"]) if row["host"] else None,
                "source_type": str(row["source_type"]),
                "cited_text_sha256": (
                    hashlib.sha256(str(row["cited_text"]).encode("utf-8")).hexdigest()
                    if row["cited_text"]
                    else None
                ),
                "capture_ref_id": str(row["capture_ref_id"]) if row["capture_ref_id"] else None,
                "source_captures": captures_by_citation.get(str(row["citation_id"]), []),
            }
            for row in citation_rows
        ]

        try:
            from .citation_support_routes import (
                load_citation_support_bundles_from_connection,
                load_fact_accuracy_bundles_from_connection,
            )
        except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
            from citation_support_routes import (  # type: ignore[no-redef]
                load_citation_support_bundles_from_connection,
                load_fact_accuracy_bundles_from_connection,
            )
        snapshot_ids = [
            str(item["snapshot_id"])
            for item in samples
            if item.get("snapshot_id")
        ]
        citation_bundles = load_citation_support_bundles_from_connection(
            conn,
            tenant_id,
            snapshot_ids,
        )
        fact_bundles = load_fact_accuracy_bundles_from_connection(
            conn,
            tenant_id,
            snapshot_ids,
        )
        for sample in samples:
            snapshot_id = str(sample.get("snapshot_id") or "")
            bundle = citation_bundles.get(snapshot_id)
            sample["citation_support_score"] = (
                bundle.metrics.citation_support_rate if bundle else None
            )

        citations_by_id = {
            str(item["citation_id"]): item for item in citations
        }
        for citation in citations:
            citation["support_reviews"] = []
        for snapshot_id in snapshot_ids:
            bundle = citation_bundles.get(snapshot_id)
            if bundle is None:
                continue
            claims_by_id = {claim.claim_id: claim for claim in bundle.claims}
            latest_by_pair: dict[tuple[str, str], Any] = {}
            for review in sorted(
                (
                    item
                    for item in bundle.reviews
                    if item.review_case_purpose != "benchmark"
                ),
                key=lambda item: (item.reviewed_at, item.review_id),
            ):
                latest_by_pair[(review.claim_id, review.citation_id)] = review
            for (claim_id, citation_id), latest in latest_by_pair.items():
                claim = claims_by_id.get(claim_id)
                citation = citations_by_id.get(citation_id)
                if claim is None or citation is None:
                    continue
                support_review = {
                    "claim_id": claim.claim_id,
                    "claim_sha256": claim.claim_sha256,
                    "answer_start": claim.answer_start,
                    "answer_end": claim.answer_end,
                    "review_id": latest.review_id,
                    "support_label": latest.support_label,
                    "evidence_grade": latest.evidence_grade,
                    "source_content_sha256": latest.source_content_sha256,
                    "source_object_ref_id": latest.source_object_ref_id,
                    "source_capture_id": latest.source_capture_id,
                    "source_segment_id": latest.source_segment_id,
                    "source_start": latest.source_start,
                    "source_end": latest.source_end,
                    "review_method": latest.review_method,
                    "reviewed_by": latest.reviewed_by,
                    "reviewed_at": _iso_value(latest.reviewed_at),
                    "review_case_id": latest.review_case_id,
                    "reviewer_role": latest.reviewer_role,
                    "review_case_status": latest.review_case_status,
                    "review_case_purpose": latest.review_case_purpose,
                    "evidence_verified": latest.evidence_verified,
                    "commercially_verified": latest.commercially_verified,
                }
                support_review["review_record_sha256"] = canonical_json_sha256(
                    support_review
                )
                citation["support_reviews"].append(support_review)

        fact_accuracy_index: list[dict[str, Any]] = []
        for snapshot_id in snapshot_ids:
            bundle = fact_bundles.get(snapshot_id)
            if bundle is None:
                continue
            for claim in bundle.claims:
                if claim.claim_kind not in {"brand_fact", "competitor_fact"}:
                    continue
                claim_reviews = sorted(
                    (
                        review
                        for review in bundle.reviews
                        if review.claim_id == claim.claim_id
                        and review.review_case_purpose != "benchmark"
                    ),
                    key=lambda review: (review.reviewed_at, review.review_id),
                )
                latest = claim_reviews[-1] if claim_reviews else None
                latest_review: dict[str, Any] | None = None
                if latest is not None:
                    latest_review = {
                        "review_id": latest.review_id,
                        "verdict": latest.verdict,
                        "evidence_grade": latest.evidence_grade,
                        "fact_revision_id": latest.fact_revision_id,
                        "knowledge_source_id": latest.knowledge_source_id,
                        "knowledge_segment_id": latest.knowledge_segment_id,
                        "fact_revision_sha256": latest.fact_revision_sha256,
                        "source_content_sha256": latest.source_content_sha256,
                        "quoted_text_sha256": latest.quoted_text_sha256,
                        "source_start": latest.source_start,
                        "source_end": latest.source_end,
                        "review_method": latest.review_method,
                        "reviewed_by": latest.reviewed_by,
                        "reviewed_at": _iso_value(latest.reviewed_at),
                        "supersedes_review_id": latest.supersedes_review_id,
                        "review_case_id": latest.review_case_id,
                        "reviewer_role": latest.reviewer_role,
                        "review_case_status": latest.review_case_status,
                        "review_case_purpose": latest.review_case_purpose,
                        "evidence_verified": latest.evidence_verified,
                        "commercially_verified": latest.commercially_verified,
                    }
                    latest_review["review_record_sha256"] = canonical_json_sha256(
                        latest_review
                    )
                fact_accuracy_index.append(
                    {
                        "claim_id": claim.claim_id,
                        "snapshot_id": claim.snapshot_id,
                        "claim_kind": claim.claim_kind,
                        "claim_sha256": claim.claim_sha256,
                        "answer_start": claim.answer_start,
                        "answer_end": claim.answer_end,
                        "subject_entity_text": claim.subject_entity_text,
                        "latest_review": latest_review,
                    }
                )

        linked_object_ids: set[str] = set()
        for sample in samples:
            linked_object_ids.update(
                value
                for value in (
                    sample["screenshot_object_ref_id"],
                    sample["source_panel_object_ref_id"],
                )
                if value
            )
        for captures in captures_by_citation.values():
            for capture in captures:
                linked_object_ids.update(
                    value
                    for value in (capture["raw_object_ref_id"], capture["text_object_ref_id"])
                    if value
                )
        object_rows = conn.execute(
            text(
                """
                SELECT id, object_type, content_type, byte_size, sha256, created_at
                FROM airank_object_refs
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY created_at, id
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        objects = [
            {
                "object_ref_id": str(row["id"]),
                "object_type": str(row["object_type"]),
                "content_type": str(row["content_type"]) if row["content_type"] else None,
                "byte_size": int(row["byte_size"]) if row["byte_size"] is not None else None,
                "sha256": str(row["sha256"]) if row["sha256"] else None,
                "created_at": _iso_value(row["created_at"]),
            }
            for row in object_rows
            if str(row["id"]) in linked_object_ids
        ]
        source_governance = self._load_source_governance(
            conn,
            tenant_id,
            project_id,
            citations,
            samples,
            evaluated_at=evaluated_at,
            evaluation_clock=evaluation_clock,
        )
        return samples, citations, fact_accuracy_index, objects, source_governance

    @staticmethod
    def _empty_source_governance(evaluated_at: datetime | None) -> dict[str, Any]:
        timestamp = evaluated_at or datetime.now(timezone.utc)
        return {
            "policy_version": SOURCE_GOVERNANCE_VERSION,
            "evaluated_at": timestamp.isoformat(),
            "entries": [],
            "unresolved_citation_ids": [],
        }

    def _load_source_governance(
        self,
        conn: Any,
        tenant_id: str,
        project_id: str,
        citations: list[dict[str, Any]],
        samples: list[dict[str, Any]],
        *,
        evaluated_at: datetime | None,
        evaluation_clock: datetime | None,
    ) -> dict[str, Any]:
        timestamp = evaluated_at or datetime.now(timezone.utc)
        clock = evaluation_clock or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if clock.tzinfo is None:
            clock = clock.replace(tzinfo=timezone.utc)
        snapshot_run = {
            str(item["snapshot_id"]): str(item["run_id"])
            for item in samples
            if item.get("snapshot_id") and item.get("run_id")
        }
        by_host: dict[str, dict[str, set[str]]] = {}
        unresolved_citation_ids: list[str] = []
        for citation in citations:
            citation_id = str(citation.get("citation_id") or "")
            try:
                normalized_host = normalize_source_host(str(citation.get("host") or ""))
            except ValueError:
                unresolved_citation_ids.append(citation_id)
                continue
            aggregate = by_host.setdefault(
                normalized_host,
                {"citation_ids": set(), "snapshot_ids": set(), "run_ids": set()},
            )
            aggregate["citation_ids"].add(citation_id)
            snapshot_id = str(citation.get("snapshot_id") or "")
            aggregate["snapshot_ids"].add(snapshot_id)
            run_id = snapshot_run.get(snapshot_id)
            if run_id:
                aggregate["run_ids"].add(run_id)

        revision_rows = conn.execute(
            text(
                """
                SELECT * FROM airank_source_classification_revisions
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY normalized_host ASC, revision_number DESC,
                         reviewed_at DESC, id DESC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
        latest_by_host: dict[str, Any] = {}
        for row in revision_rows:
            host = str(row["normalized_host"])
            if host in by_host and host not in latest_by_host:
                latest_by_host[host] = row

        state_timestamp = timestamp
        for row in latest_by_host.values():
            reviewed_at = _datetime_value(row["reviewed_at"])
            state_timestamp = max(state_timestamp, reviewed_at)
            if row["valid_until"] is not None:
                valid_until = _datetime_value(row["valid_until"])
                if valid_until < clock:
                    state_timestamp = max(
                        state_timestamp,
                        valid_until + timedelta(microseconds=1),
                    )

        entries: list[dict[str, Any]] = []
        for normalized_host in sorted(by_host):
            aggregate = by_host[normalized_host]
            row = latest_by_host.get(normalized_host)
            current_revision: dict[str, Any] | None = None
            classification_status = "unclassified"
            if row is not None:
                reviewed_at = _datetime_value(row["reviewed_at"])
                valid_until = (
                    _datetime_value(row["valid_until"])
                    if row["valid_until"] is not None
                    else None
                )
                classification_status = str(row["classification_status"])
                current_revision = {
                    "revision_id": str(row["id"]),
                    "revision_number": int(row["revision_number"]),
                    "normalized_host": normalized_host,
                    "source_category_l1": str(row["source_category_l1"]),
                    "source_type": str(row["source_type"]),
                    "ecosystem": str(row["ecosystem"]) if row["ecosystem"] else None,
                    "classification_status": classification_status,
                    "classification_method": str(row["classification_method"]),
                    "classification_confidence": str(row["classification_confidence"]),
                    "authority_level": str(row["authority_level"]),
                    "usage_policy": str(row["usage_policy"]),
                    "risk_level": str(row["risk_level"]),
                    "evidence_note_sha256": hashlib.sha256(
                        str(row["evidence_note"]).encode("utf-8")
                    ).hexdigest(),
                    "evidence_url": str(row["evidence_url"]) if row["evidence_url"] else None,
                    "source_dataset_name": (
                        str(row["source_dataset_name"])
                        if row["source_dataset_name"]
                        else None
                    ),
                    "source_dataset_version": (
                        str(row["source_dataset_version"])
                        if row["source_dataset_version"]
                        else None
                    ),
                    "valid_until": valid_until.isoformat() if valid_until else None,
                    "reviewed_by": str(row["reviewed_by"]),
                    "reviewed_at": reviewed_at.isoformat(),
                    "supersedes_revision_id": (
                        str(row["supersedes_revision_id"])
                        if row["supersedes_revision_id"]
                        else None
                    ),
                    "request_sha256": str(row["request_sha256"]),
                    "effective": valid_until is None or valid_until >= state_timestamp,
                }
                current_revision["revision_record_sha256"] = canonical_json_sha256(
                    current_revision
                )
            entries.append(
                {
                    "normalized_host": normalized_host,
                    "citation_ids": sorted(aggregate["citation_ids"]),
                    "snapshot_ids": sorted(aggregate["snapshot_ids"]),
                    "run_ids": sorted(aggregate["run_ids"]),
                    "classification_status": classification_status,
                    "current_revision": current_revision,
                }
            )
        return {
            "policy_version": SOURCE_GOVERNANCE_VERSION,
            "evaluated_at": state_timestamp.isoformat(),
            "entries": entries,
            "unresolved_citation_ids": sorted(unresolved_citation_ids),
        }

    def _insert_object_ref(
        self,
        conn: Any,
        *,
        object_ref_id: str,
        tenant_id: str,
        project_id: str,
        stored: Any,
        packet_id: str,
        created_at: datetime,
    ) -> None:
        insert_prefix = "INSERT OR IGNORE" if self._engine.dialect.name == "sqlite" else "INSERT IGNORE"
        conn.execute(
            text(
                f"""
                {insert_prefix} INTO airank_object_refs (
                  id, tenant_id, project_id, object_type, object_uri,
                  content_type, byte_size, sha256, metadata_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, 'report_evidence_packet', :object_uri,
                  :content_type, :byte_size, :sha256, :metadata_json, :created_at
                )
                """
            ),
            {
                "id": object_ref_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "object_uri": stored.uri,
                "content_type": stored.content_type,
                "byte_size": stored.byte_size,
                "sha256": stored.sha256,
                "metadata_json": json.dumps(
                    {
                        "immutable": True,
                        "packet_id": packet_id,
                        "object_key": stored.key,
                        "storage_driver": stored.driver,
                    },
                    sort_keys=True,
                ),
                "created_at": created_at,
            },
        )

    def _find_by_idempotency_key(self, conn: Any, tenant_id: str, idempotency_key: str) -> Any:
        return self._packet_query(
            conn,
            "p.tenant_id=:tenant_id AND p.idempotency_key=:idempotency_key",
            {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
        )

    def _find_for_report(self, conn: Any, tenant_id: str, report_id: str) -> Any:
        return self._packet_query(
            conn,
            "p.tenant_id=:tenant_id AND p.report_id=:report_id AND p.schema_version=:schema_version",
            {
                "tenant_id": tenant_id,
                "report_id": report_id,
                "schema_version": REPORT_EVIDENCE_PACKET_VERSION,
            },
        )

    def _find_by_content(
        self,
        conn: Any,
        tenant_id: str,
        report_id: str,
        content_sha256: str,
    ) -> Any:
        return self._packet_query(
            conn,
            "p.tenant_id=:tenant_id AND p.report_id=:report_id "
            "AND p.schema_version=:schema_version AND p.content_sha256=:content_sha256",
            {
                "tenant_id": tenant_id,
                "report_id": report_id,
                "schema_version": REPORT_EVIDENCE_PACKET_VERSION,
                "content_sha256": content_sha256,
            },
        )

    def _find_latest_for_report(self, conn: Any, tenant_id: str, report_id: str) -> Any:
        return self._packet_query(
            conn,
            "p.tenant_id=:tenant_id AND p.report_id=:report_id",
            {"tenant_id": tenant_id, "report_id": report_id},
        )

    def _packet_object_status(self, row: Any) -> str:
        metadata = _json_value(row.get("object_metadata_json"), {})
        object_key = str(metadata.get("object_key") or "")
        stored_driver = str(metadata.get("storage_driver") or "")
        if not object_key:
            return "missing"
        storage = self._storage()
        if not stored_driver or storage.driver != stored_driver:
            return "driver_mismatch"
        try:
            payload = storage.get_bytes(object_key)
        except ObjectStorageError:
            return "missing"
        packet_sha256 = str(row["content_sha256"])
        expected_sha256 = str(row.get("object_sha256") or "")
        packet_size = int(row["byte_size"])
        expected_size = int(row.get("object_byte_size") or 0)
        if expected_sha256 != packet_sha256 or expected_size != packet_size:
            return "integrity_failed"
        if hashlib.sha256(payload).hexdigest() != expected_sha256 or len(payload) != expected_size:
            return "integrity_failed"
        return "available"

    @staticmethod
    def _raise_object_unavailable(row: Any, *, reason: str) -> None:
        raise StarletteHTTPException(
            status_code=503,
            detail={
                "code": "EVIDENCE_OBJECT_UNAVAILABLE",
                "details": {
                    "object_ref_id": str(row["object_ref_id"]),
                    "reason": reason,
                },
            },
        )

    @staticmethod
    def _raise_object_integrity_failed(row: Any) -> None:
        raise StarletteHTTPException(
            status_code=409,
            detail={
                "code": "EVIDENCE_INTEGRITY_FAILED",
                "details": {"object_ref_id": str(row["object_ref_id"])},
            },
        )

    def _restore_packet_object(
        self,
        row: Any,
        *,
        packet: Any,
        created_by: str,
        trace_id: str,
        restored_at: datetime,
    ) -> ReportEvidencePacketData:
        metadata = _json_value(row.get("object_metadata_json"), {})
        object_key = str(metadata.get("object_key") or "")
        if not object_key:
            self._raise_object_unavailable(row, reason="object_key_missing")
        try:
            stored = self._storage().put_bytes(
                packet.canonical_bytes,
                key=object_key,
                content_type="application/json",
            )
        except ObjectStorageError as exc:
            raise StarletteHTTPException(
                status_code=503,
                detail={
                    "code": "EVIDENCE_OBJECT_UNAVAILABLE",
                    "details": {
                        "object_ref_id": str(row["object_ref_id"]),
                        "reason": "object_restore_failed",
                        "error_type": type(exc).__name__,
                    },
                },
            ) from exc
        if stored.sha256 != str(row["content_sha256"]):
            self._raise_object_integrity_failed(row)

        repaired_metadata = {
            **metadata,
            "immutable": True,
            "object_key": stored.key,
            "storage_driver": stored.driver,
        }
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE airank_object_refs
                    SET object_uri=:object_uri, content_type=:content_type,
                        byte_size=:byte_size, sha256=:sha256, metadata_json=:metadata_json
                    WHERE tenant_id=:tenant_id AND id=:object_ref_id
                    """
                ),
                {
                    "object_uri": stored.uri,
                    "content_type": stored.content_type,
                    "byte_size": stored.byte_size,
                    "sha256": stored.sha256,
                    "metadata_json": json.dumps(repaired_metadata, sort_keys=True),
                    "tenant_id": str(row["tenant_id"]),
                    "object_ref_id": str(row["object_ref_id"]),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO airank_audit_events (
                      id, tenant_id, project_id, event_type, entity_type,
                      entity_id, trace_id, payload_json, created_at
                    ) VALUES (
                      :id, :tenant_id, :project_id,
                      'report.evidence_packet_object_restored',
                      'report_evidence_packet', :entity_id, :trace_id,
                      :payload_json, :created_at
                    )
                    """
                ),
                {
                    "id": f"audit_{uuid4().hex[:20]}",
                    "tenant_id": str(row["tenant_id"]),
                    "project_id": str(row["project_id"]),
                    "entity_id": str(row["id"]),
                    "trace_id": trace_id,
                    "payload_json": json.dumps(
                        {
                            "report_id": str(row["report_id"]),
                            "packet_id": str(row["id"]),
                            "content_sha256": stored.sha256,
                            "object_ref_id": str(row["object_ref_id"]),
                            "restored_by": created_by,
                        },
                        sort_keys=True,
                    ),
                    "created_at": restored_at,
                },
            )
            repaired = self._find_by_content(
                conn,
                str(row["tenant_id"]),
                str(row["report_id"]),
                stored.sha256,
            )
        assert repaired is not None
        return self._packet_data(repaired, replay=True)

    @staticmethod
    def _packet_query(conn: Any, where_clause: str, params: dict[str, Any]) -> Any:
        return conn.execute(
            text(
                f"""
                SELECT p.*, o.content_type,
                       o.byte_size AS object_byte_size,
                       o.sha256 AS object_sha256,
                       o.metadata_json AS object_metadata_json
                FROM airank_report_evidence_packets p
                JOIN airank_object_refs o
                  ON o.tenant_id=p.tenant_id AND o.id=p.object_ref_id
                WHERE {where_clause}
                ORDER BY p.created_at DESC, p.id DESC
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()

    @staticmethod
    def _packet_data(row: Any, *, replay: bool) -> ReportEvidencePacketData:
        summary = _json_value(row["summary_json"], {})
        return ReportEvidencePacketData(
            packet_id=str(row["id"]),
            report_id=str(row["report_id"]),
            tenant_id=str(row["tenant_id"]),
            project_id=str(row["project_id"]),
            schema_version=str(row["schema_version"]),
            status="ready",
            object_ref_id=str(row["object_ref_id"]),
            integrity_audit_id=(
                str(row["integrity_audit_id"])
                if row.get("integrity_audit_id")
                else None
            ),
            content_url=f"/api/v1/evidence-objects/{row['object_ref_id']}/content",
            content_type=str(row["content_type"]),
            byte_size=int(row["byte_size"]),
            content_sha256=str(row["content_sha256"]),
            report_sha256=str(row["report_sha256"]),
            created_by=str(row["created_by"]),
            created_at=_datetime_value(row["created_at"]),
            summary=ReportEvidencePacketSummary(
                sample_count=int(summary.get("samples", 0)),
                citation_count=int(summary.get("citations", 0)),
                fact_claim_count=int(summary.get("fact_claims", 0)),
                fact_accuracy_review_count=int(summary.get("fact_accuracy_reviews", 0)),
                source_host_count=int(summary.get("source_hosts", 0)),
                source_effective_classification_count=int(
                    summary.get("source_effective_classifications", 0)
                ),
                source_authority_resolved_count=int(
                    summary.get("source_authority_resolved", 0)
                ),
                source_authority_coverage_rate=(
                    float(summary["source_authority_coverage_rate"])
                    if summary.get("source_authority_coverage_rate") is not None
                    else None
                ),
                source_authority_summary_eligible=bool(
                    summary.get("source_authority_summary_eligible", False)
                ),
                evidence_object_count=int(summary.get("evidence_objects", 0)),
                known_limitation_count=int(summary.get("known_limitations", 0)),
            ),
            idempotent_replay=replay,
        )


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _iso_value(value: Any) -> str | None:
    if value is None:
        return None
    return _datetime_value(value).isoformat()
