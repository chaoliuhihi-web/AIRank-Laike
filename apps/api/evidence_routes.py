from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_evidence import ObjectStorageError, build_object_storage_from_env, sha256_bytes


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["evidence-center"])


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


class AnswerSampleData(BaseModel):
    snapshot_id: str
    run_id: str
    task_id: Optional[str]
    question_id: str
    provider: str
    cohort_type: str
    prompt_version_id: str
    sample_index: int
    session_id: str
    collector_surface: str
    evidence_level: str
    sample_status: str
    answer_excerpt: str
    answer_sha256: str
    brand_mentioned: bool
    brand_rank: Optional[int]
    mention_class: str
    model_name: Optional[str]
    search_enabled: Optional[bool]
    external_trace_id: Optional[str]
    citation_count: int
    created_at: datetime


class CitationData(BaseModel):
    citation_id: str
    citation_order: int
    title: Optional[str]
    url: str
    host: Optional[str]
    source_type: Optional[str]
    cited_text: Optional[str]
    relevance_score: Optional[float]
    metadata: dict[str, Any]


class EvidenceObjectData(BaseModel):
    object_ref_id: Optional[str]
    object_uri: Optional[str]
    content_type: Optional[str]
    byte_size: Optional[int]
    sha256: Optional[str]
    content_url: Optional[str]


@dataclass(frozen=True)
class EvidenceObjectContent:
    payload: bytes
    content_type: str
    sha256: str


class AnswerSampleDetailData(AnswerSampleData):
    project_id: str
    answer_text: str
    raw_response_sha256: str
    raw_response: dict[str, Any]
    request_metadata: dict[str, Any]
    evidence_snapshot_id: str
    evidence_captured_at: datetime
    screenshot: EvidenceObjectData
    source_panel: EvidenceObjectData
    citations: list[CitationData]


class AnswerSampleListResponse(BaseModel):
    data: list[AnswerSampleData]
    meta: "AnswerSampleListMeta"


class AnswerSampleListMeta(BaseModel):
    trace_id: str
    request_id: str
    run_id: Optional[str]
    limit: int
    total: int
    valid_count: int
    valid_unmentioned_count: int
    citation_sample_count: int


class AnswerSampleDetailResponse(BaseModel):
    data: AnswerSampleDetailData
    meta: dict[str, str]


class EvidenceRepository(Protocol):
    def list_samples(
        self,
        tenant_id: str,
        project_id: str,
        run_id: Optional[str],
        limit: int,
    ) -> tuple[list[AnswerSampleData], dict[str, int]]: ...
    def get_sample(self, tenant_id: str, snapshot_id: str) -> AnswerSampleDetailData: ...
    def read_object(self, tenant_id: str, object_ref_id: str) -> EvidenceObjectContent: ...


class InMemoryEvidenceRepository:
    def list_samples(
        self,
        tenant_id: str,
        project_id: str,
        run_id: Optional[str],
        limit: int,
    ) -> tuple[list[AnswerSampleData], dict[str, int]]:
        del tenant_id, project_id, run_id, limit
        return [], {
            "total": 0,
            "valid_count": 0,
            "valid_unmentioned_count": 0,
            "citation_sample_count": 0,
        }

    def get_sample(self, tenant_id: str, snapshot_id: str) -> AnswerSampleDetailData:
        del tenant_id
        raise StarletteHTTPException(
            status_code=404,
            detail={"code": "OBJECT_REF_NOT_FOUND", "details": {"snapshot_id": snapshot_id}},
        )

    def read_object(self, tenant_id: str, object_ref_id: str) -> EvidenceObjectContent:
        del tenant_id
        raise StarletteHTTPException(
            status_code=404,
            detail={"code": "OBJECT_REF_NOT_FOUND", "details": {"object_ref_id": object_ref_id}},
        )


class MySQLEvidenceRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _summary(row: Mapping[str, Any]) -> AnswerSampleData:
        answer_text = str(row["answer_text"] or "")
        excerpt = answer_text if len(answer_text) <= 320 else f"{answer_text[:320]}…"
        return AnswerSampleData(
            snapshot_id=row["id"],
            run_id=row["run_id"],
            task_id=row["task_id"],
            question_id=row["question_id"],
            provider=row["provider"],
            cohort_type=row["cohort_type"],
            prompt_version_id=row["prompt_version_id"],
            sample_index=row["sample_index"],
            session_id=row["session_id"],
            collector_surface=row["collector_surface"],
            evidence_level=row["evidence_level"],
            sample_status=row["sample_status"],
            answer_excerpt=excerpt,
            answer_sha256=row["answer_sha256"],
            brand_mentioned=bool(row["brand_mentioned"]),
            brand_rank=row["brand_rank"],
            mention_class=row["mention_class"],
            model_name=row["model_name"],
            search_enabled=bool(row["search_enabled"]) if row["search_enabled"] is not None else None,
            external_trace_id=row["external_trace_id"],
            citation_count=int(row["citation_count"] or 0),
            created_at=row["created_at"],
        )

    def list_samples(
        self,
        tenant_id: str,
        project_id: str,
        run_id: Optional[str],
        limit: int,
    ) -> tuple[list[AnswerSampleData], dict[str, int]]:
        with self.engine.begin() as conn:
            project = conn.execute(
                text(
                    """
                    SELECT id FROM airank_projects
                    WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).first()
            if project is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "PROJECT_NOT_FOUND", "details": {"project_id": project_id}},
                )
            run_filter = " AND s.run_id=:run_id" if run_id else ""
            params = {"tenant_id": tenant_id, "project_id": project_id, "limit": limit, "run_id": run_id}
            aggregate = conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN s.sample_status='valid' THEN 1 ELSE 0 END) AS valid_count,
                           SUM(CASE WHEN s.sample_status='valid' AND s.brand_mentioned=0 THEN 1 ELSE 0 END)
                             AS valid_unmentioned_count,
                           SUM(CASE WHEN EXISTS (
                               SELECT 1 FROM airank_source_citations c
                               WHERE c.tenant_id=s.tenant_id AND c.snapshot_id=s.id
                           ) THEN 1 ELSE 0 END) AS citation_sample_count
                    FROM airank_answer_snapshots s
                    WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id{run_filter}
                    """
                ),
                params,
            ).mappings().one()
            rows = conn.execute(
                text(
                    f"""
                    SELECT s.*,
                           (SELECT COUNT(*) FROM airank_source_citations c
                            WHERE c.tenant_id=s.tenant_id AND c.snapshot_id=s.id) AS citation_count
                    FROM airank_answer_snapshots s
                    WHERE s.tenant_id=:tenant_id AND s.project_id=:project_id
                    {run_filter}
                    ORDER BY s.created_at DESC, s.id DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [self._summary(row) for row in rows], {
            "total": int(aggregate["total"] or 0),
            "valid_count": int(aggregate["valid_count"] or 0),
            "valid_unmentioned_count": int(aggregate["valid_unmentioned_count"] or 0),
            "citation_sample_count": int(aggregate["citation_sample_count"] or 0),
        }

    def get_sample(self, tenant_id: str, snapshot_id: str) -> AnswerSampleDetailData:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT s.*,
                           e.id AS evidence_snapshot_id,
                           e.raw_response_json,
                           e.raw_response_sha256 AS evidence_raw_response_sha256,
                           e.request_metadata_json,
                           e.captured_at AS evidence_captured_at,
                           e.screenshot_ref_id AS evidence_screenshot_ref_id,
                           e.source_panel_ref_id AS evidence_source_panel_ref_id,
                           (SELECT COUNT(*) FROM airank_source_citations c
                            WHERE c.tenant_id=s.tenant_id AND c.snapshot_id=s.id) AS citation_count
                    FROM airank_answer_snapshots s
                    JOIN airank_evidence_snapshots e
                      ON e.tenant_id=s.tenant_id AND e.answer_snapshot_id=s.id
                    WHERE s.tenant_id=:tenant_id AND s.id=:snapshot_id
                    """
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).mappings().first()
            if row is None:
                raise StarletteHTTPException(
                    status_code=404,
                    detail={"code": "OBJECT_REF_NOT_FOUND", "details": {"snapshot_id": snapshot_id}},
                )
            citations = conn.execute(
                text(
                    """
                    SELECT * FROM airank_source_citations
                    WHERE tenant_id=:tenant_id AND snapshot_id=:snapshot_id
                    ORDER BY citation_order ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "snapshot_id": snapshot_id},
            ).mappings().all()
            object_ids = [
                object_id
                for object_id in (
                    row["evidence_screenshot_ref_id"],
                    row["evidence_source_panel_ref_id"],
                )
                if object_id
            ]
            objects: dict[str, Mapping[str, Any]] = {}
            for object_id in object_ids:
                object_row = conn.execute(
                    text(
                        """
                        SELECT id, object_uri, content_type, byte_size, sha256
                        FROM airank_object_refs
                        WHERE tenant_id=:tenant_id AND id=:object_id
                        """
                    ),
                    {"tenant_id": tenant_id, "object_id": object_id},
                ).mappings().first()
                if object_row is not None:
                    objects[str(object_id)] = object_row

        summary = self._summary(row)
        screenshot = self._object_data(objects.get(str(row["evidence_screenshot_ref_id"])))
        source_panel = self._object_data(objects.get(str(row["evidence_source_panel_ref_id"])))
        return AnswerSampleDetailData(
            **summary.model_dump(),
            project_id=row["project_id"],
            answer_text=row["answer_text"],
            raw_response_sha256=row["evidence_raw_response_sha256"],
            raw_response=self._json_object(row["raw_response_json"]),
            request_metadata=self._json_object(row["request_metadata_json"]),
            evidence_snapshot_id=row["evidence_snapshot_id"],
            evidence_captured_at=row["evidence_captured_at"],
            screenshot=screenshot,
            source_panel=source_panel,
            citations=[
                CitationData(
                    citation_id=citation["id"],
                    citation_order=citation["citation_order"],
                    title=citation["title"],
                    url=citation["url"],
                    host=citation["host"],
                    source_type=citation["source_type"],
                    cited_text=citation["cited_text"],
                    relevance_score=(
                        float(citation["relevance_score"])
                        if citation["relevance_score"] is not None
                        else None
                    ),
                    metadata=self._json_object(citation["metadata_json"]),
                )
                for citation in citations
            ],
        )

    def read_object(self, tenant_id: str, object_ref_id: str) -> EvidenceObjectContent:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, content_type, byte_size, sha256, metadata_json
                    FROM airank_object_refs
                    WHERE tenant_id=:tenant_id AND id=:object_ref_id
                    """
                ),
                {"tenant_id": tenant_id, "object_ref_id": object_ref_id},
            ).mappings().first()
        if row is None:
            raise StarletteHTTPException(
                status_code=404,
                detail={"code": "OBJECT_REF_NOT_FOUND", "details": {"object_ref_id": object_ref_id}},
            )

        metadata = self._json_object(row["metadata_json"])
        object_key = str(metadata.get("object_key") or "")
        stored_driver = str(metadata.get("storage_driver") or "")
        expected_sha256 = str(row["sha256"] or "")
        if not object_key or not stored_driver or not expected_sha256:
            raise StarletteHTTPException(
                status_code=503,
                detail={"code": "EVIDENCE_OBJECT_UNAVAILABLE", "details": {"object_ref_id": object_ref_id}},
            )
        try:
            storage = build_object_storage_from_env()
            if storage.driver != stored_driver:
                raise ObjectStorageError("configured storage driver does not match evidence record")
            payload = storage.get_bytes(object_key)
        except ObjectStorageError as exc:
            raise StarletteHTTPException(
                status_code=503,
                detail={"code": "EVIDENCE_OBJECT_UNAVAILABLE", "details": {"object_ref_id": object_ref_id}},
            ) from exc

        actual_sha256 = sha256_bytes(payload)
        expected_size = int(row["byte_size"]) if row["byte_size"] is not None else None
        if actual_sha256 != expected_sha256 or (expected_size is not None and len(payload) != expected_size):
            raise StarletteHTTPException(
                status_code=409,
                detail={"code": "EVIDENCE_INTEGRITY_FAILED", "details": {"object_ref_id": object_ref_id}},
            )
        return EvidenceObjectContent(
            payload=payload,
            content_type=str(row["content_type"] or "application/octet-stream"),
            sha256=expected_sha256,
        )

    @staticmethod
    def _json_object(value: object) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value or "{}")
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}

    @staticmethod
    def _object_data(row: Mapping[str, Any] | None) -> EvidenceObjectData:
        if row is None:
            return EvidenceObjectData(
                object_ref_id=None,
                object_uri=None,
                content_type=None,
                byte_size=None,
                sha256=None,
                content_url=None,
            )
        return EvidenceObjectData(
            object_ref_id=row["id"],
            object_uri=row["object_uri"],
            content_type=row["content_type"],
            byte_size=row["byte_size"],
            sha256=row["sha256"],
            content_url=f"/api/v1/evidence-objects/{row['id']}/content",
        )


def build_repository() -> EvidenceRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLEvidenceRepository(database_url) if database_url else InMemoryEvidenceRepository()


EVIDENCE_REPOSITORY: EvidenceRepository = build_repository()


@router.get("/projects/{project_id}/samples", response_model=AnswerSampleListResponse)
def list_answer_samples(
    project_id: str,
    run_id: Optional[str] = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=200, ge=1, le=1000),
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> AnswerSampleListResponse:
    samples, aggregates = EVIDENCE_REPOSITORY.list_samples(tenant_id, project_id, run_id, limit)
    return AnswerSampleListResponse(
        data=samples,
        meta=AnswerSampleListMeta(
            **response_meta(trace_id),
            run_id=run_id,
            limit=limit,
            **aggregates,
        ),
    )


@router.get("/samples/{snapshot_id}", response_model=AnswerSampleDetailResponse)
def get_answer_sample(
    snapshot_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> AnswerSampleDetailResponse:
    return AnswerSampleDetailResponse(
        data=EVIDENCE_REPOSITORY.get_sample(tenant_id, snapshot_id),
        meta=response_meta(trace_id),
    )


@router.get("/evidence-objects/{object_ref_id}/content")
def get_evidence_object_content(
    object_ref_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
) -> Response:
    evidence_object = EVIDENCE_REPOSITORY.read_object(tenant_id, object_ref_id)
    return Response(
        content=evidence_object.payload,
        media_type=evidence_object.content_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "ETag": f'"sha256-{evidence_object.sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
