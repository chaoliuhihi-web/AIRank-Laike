from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from threading import Lock
from typing import Any, Literal, Mapping, Optional, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import create_engine, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from airank_evidence import normalize_source_host


TRACE_HEADER = "X-AIRank-Trace-Id"
router = APIRouter(prefix="/api/v1", tags=["source-registry"])

SourceCategoryL1 = Literal[
    "brand_corporate",
    "government_public",
    "news_media",
    "vertical_professional",
    "platform_community",
    "business_services",
    "research_documentation",
    "search_page_proxy",
    "other",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"unsupported datetime {value!r}")


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def trusted_actor(requested_actor: str, authenticated_actor: Optional[str]) -> str:
    if authenticated_actor:
        return authenticated_actor
    enforcement = os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower()
    if enforcement in {"0", "false", "disabled", "off"}:
        return requested_actor
    raise StarletteHTTPException(status_code=401, detail={"code": "AUTH_TOKEN_INVALID"})


def validate_evidence_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip()
    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("evidence URL is invalid") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("evidence URL must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ValueError("evidence URL must not contain credentials or a fragment")
    return normalized


class SourceClassificationReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_category_l1: SourceCategoryL1
    source_type: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_\-]+$")
    ecosystem: Optional[str] = Field(default=None, max_length=160)
    classification_confidence: Literal["low", "medium", "high"]
    authority_level: Literal["unknown", "low", "medium", "high", "official"]
    usage_policy: Literal["primary_evidence", "context_only", "lead_only", "prohibited"]
    risk_level: Literal["low", "medium", "high", "critical"]
    evidence_note: str = Field(min_length=8, max_length=4000)
    evidence_url: Optional[str] = Field(default=None, max_length=2048)
    valid_until: Optional[datetime] = None
    reviewed_by: str = Field(min_length=1, max_length=64)
    supersedes_revision_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("evidence_url")
    @classmethod
    def evidence_url_must_be_safe(cls, value: Optional[str]) -> Optional[str]:
        return validate_evidence_url(value)


class SourceClassificationRevisionData(BaseModel):
    revision_id: str
    revision_number: int
    normalized_host: str
    source_category_l1: SourceCategoryL1
    source_type: str
    ecosystem: Optional[str]
    classification_status: Literal["reviewed", "curated"]
    classification_method: Literal["human_review", "dataset_import"]
    classification_confidence: Literal["low", "medium", "high"]
    authority_level: Literal["unknown", "low", "medium", "high", "official"]
    usage_policy: Literal["primary_evidence", "context_only", "lead_only", "prohibited"]
    risk_level: Literal["low", "medium", "high", "critical"]
    evidence_note: str
    evidence_url: Optional[str]
    source_dataset_name: Optional[str]
    source_dataset_version: Optional[str]
    valid_until: Optional[datetime]
    reviewed_by: str
    reviewed_at: datetime
    supersedes_revision_id: Optional[str]
    request_sha256: str
    effective: bool
    idempotent_replay: bool = False


class SourceRegistryEntryData(BaseModel):
    tenant_id: str
    project_id: str
    normalized_host: str
    reviewable: bool
    citation_count: int
    sample_count: int
    provider_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    classification_status: Literal["unclassified", "reviewed", "curated"]
    current_revision: Optional[SourceClassificationRevisionData]
    history: list[SourceClassificationRevisionData]


class SourceRegistryListResponse(BaseModel):
    data: list[SourceRegistryEntryData]
    meta: dict[str, Any]


class SourceRegistryEntryResponse(BaseModel):
    data: SourceRegistryEntryData
    meta: dict[str, str]


def classification_request_sha256(
    tenant_id: str,
    project_id: str,
    normalized_host: str,
    payload: SourceClassificationReviewRequest,
) -> str:
    document = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "normalized_host": normalized_host,
        "review": payload.model_dump(mode="json", exclude_none=True),
    }
    encoded = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SourceRegistryRepository(Protocol):
    def list(self, tenant_id: str, project_id: str) -> list[SourceRegistryEntryData]: ...

    def get(
        self, tenant_id: str, project_id: str, normalized_host: str
    ) -> SourceRegistryEntryData: ...

    def review(
        self,
        tenant_id: str,
        project_id: str,
        normalized_host: str,
        payload: SourceClassificationReviewRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> SourceRegistryEntryData: ...


class InMemorySourceRegistryRepository:
    def __init__(self) -> None:
        self._projects: set[tuple[str, str]] = set()
        self._sources: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._revisions: dict[tuple[str, str, str], list[SourceClassificationRevisionData]] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, str, str, str]] = {}
        self._lock = Lock()

    def seed_project(self, tenant_id: str, project_id: str) -> None:
        self._projects.add((tenant_id, project_id))

    def seed_source(
        self,
        *,
        tenant_id: str,
        project_id: str,
        host: str,
        citation_count: int = 1,
        sample_count: int = 1,
        provider_count: int = 1,
        observed_at: Optional[datetime] = None,
    ) -> None:
        normalized_host = normalize_source_host(host)
        self.seed_project(tenant_id, project_id)
        timestamp = observed_at or utc_now()
        self._sources[(tenant_id, project_id, normalized_host)] = {
            "citation_count": citation_count,
            "sample_count": sample_count,
            "provider_count": provider_count,
            "first_seen_at": timestamp,
            "last_seen_at": timestamp,
        }

    @staticmethod
    def _with_effective(
        revision: SourceClassificationRevisionData,
        *,
        replay: bool = False,
    ) -> SourceClassificationRevisionData:
        effective = revision.valid_until is None or as_utc(revision.valid_until) >= utc_now()
        return revision.model_copy(
            update={"effective": effective, "idempotent_replay": replay}
        )

    def _entry(
        self, tenant_id: str, project_id: str, normalized_host: str, *, history: bool
    ) -> SourceRegistryEntryData:
        source = self._sources.get((tenant_id, project_id, normalized_host))
        if source is None:
            raise StarletteHTTPException(
                404, detail={"code": "SOURCE_REGISTRY_ENTRY_NOT_FOUND"}
            )
        revisions = self._revisions.get((tenant_id, project_id, normalized_host), [])
        ordered = sorted(revisions, key=lambda item: item.revision_number, reverse=True)
        current = self._with_effective(ordered[0]) if ordered else None
        return SourceRegistryEntryData(
            tenant_id=tenant_id,
            project_id=project_id,
            normalized_host=normalized_host,
            reviewable=True,
            **source,
            classification_status=current.classification_status if current else "unclassified",
            current_revision=current,
            history=[self._with_effective(item) for item in ordered] if history else [],
        )

    def list(self, tenant_id: str, project_id: str) -> list[SourceRegistryEntryData]:
        if (tenant_id, project_id) not in self._projects:
            raise StarletteHTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})
        hosts = sorted(
            host
            for row_tenant, row_project, host in self._sources
            if row_tenant == tenant_id and row_project == project_id
        )
        return [self._entry(tenant_id, project_id, host, history=False) for host in hosts]

    def get(
        self, tenant_id: str, project_id: str, normalized_host: str
    ) -> SourceRegistryEntryData:
        if (tenant_id, project_id) not in self._projects:
            raise StarletteHTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})
        return self._entry(tenant_id, project_id, normalized_host, history=True)

    def review(
        self,
        tenant_id: str,
        project_id: str,
        normalized_host: str,
        payload: SourceClassificationReviewRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> SourceRegistryEntryData:
        del trace_id
        request_sha256 = classification_request_sha256(
            tenant_id, project_id, normalized_host, payload
        )
        with self._lock:
            existing_idempotency = self._idempotency.get((tenant_id, idempotency_key))
            if existing_idempotency:
                existing_hash, existing_project, existing_host, revision_id = existing_idempotency
                if (
                    existing_hash != request_sha256
                    or existing_project != project_id
                    or existing_host != normalized_host
                ):
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                entry = self._entry(tenant_id, project_id, normalized_host, history=True)
                history = [
                    self._with_effective(
                        item,
                        replay=item.revision_id == revision_id,
                    )
                    for item in entry.history
                ]
                return entry.model_copy(
                    update={
                        "current_revision": history[0] if history else None,
                        "history": history,
                    }
                )
            self._entry(tenant_id, project_id, normalized_host, history=False)
            revisions = self._revisions.setdefault(
                (tenant_id, project_id, normalized_host), []
            )
            current = max(revisions, key=lambda item: item.revision_number) if revisions else None
            expected = current.revision_id if current else None
            if payload.supersedes_revision_id != expected:
                raise StarletteHTTPException(
                    409,
                    detail={
                        "code": "SOURCE_CLASSIFICATION_VERSION_CONFLICT",
                        "details": {"expected_revision_id": expected},
                    },
                )
            now = utc_now()
            revision = SourceClassificationRevisionData(
                revision_id=f"source_class_{uuid4().hex}",
                revision_number=(current.revision_number + 1) if current else 1,
                normalized_host=normalized_host,
                source_category_l1=payload.source_category_l1,
                source_type=payload.source_type,
                ecosystem=payload.ecosystem,
                classification_status="reviewed",
                classification_method="human_review",
                classification_confidence=payload.classification_confidence,
                authority_level=payload.authority_level,
                usage_policy=payload.usage_policy,
                risk_level=payload.risk_level,
                evidence_note=payload.evidence_note,
                evidence_url=payload.evidence_url,
                source_dataset_name=None,
                source_dataset_version=None,
                valid_until=payload.valid_until,
                reviewed_by=payload.reviewed_by,
                reviewed_at=now,
                supersedes_revision_id=payload.supersedes_revision_id,
                request_sha256=request_sha256,
                effective=payload.valid_until is None or as_utc(payload.valid_until) >= now,
            )
            revisions.append(revision)
            self._idempotency[(tenant_id, idempotency_key)] = (
                request_sha256,
                project_id,
                normalized_host,
                revision.revision_id,
            )
            return self._entry(tenant_id, project_id, normalized_host, history=True)


class MySQLSourceRegistryRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True)

    @staticmethod
    def _revision(
        row: Mapping[str, Any], *, replay: bool = False
    ) -> SourceClassificationRevisionData:
        valid_until = as_utc(row["valid_until"]) if row["valid_until"] else None
        return SourceClassificationRevisionData(
            revision_id=str(row["id"]),
            revision_number=int(row["revision_number"]),
            normalized_host=str(row["normalized_host"]),
            source_category_l1=str(row["source_category_l1"]),
            source_type=str(row["source_type"]),
            ecosystem=str(row["ecosystem"]) if row["ecosystem"] is not None else None,
            classification_status=str(row["classification_status"]),
            classification_method=str(row["classification_method"]),
            classification_confidence=str(row["classification_confidence"]),
            authority_level=str(row["authority_level"]),
            usage_policy=str(row["usage_policy"]),
            risk_level=str(row["risk_level"]),
            evidence_note=str(row["evidence_note"]),
            evidence_url=str(row["evidence_url"]) if row["evidence_url"] else None,
            source_dataset_name=(
                str(row["source_dataset_name"]) if row["source_dataset_name"] else None
            ),
            source_dataset_version=(
                str(row["source_dataset_version"])
                if row["source_dataset_version"]
                else None
            ),
            valid_until=valid_until,
            reviewed_by=str(row["reviewed_by"]),
            reviewed_at=as_utc(row["reviewed_at"]),
            supersedes_revision_id=(
                str(row["supersedes_revision_id"])
                if row["supersedes_revision_id"]
                else None
            ),
            request_sha256=str(row["request_sha256"]),
            effective=valid_until is None or valid_until >= utc_now(),
            idempotent_replay=replay,
        )

    @staticmethod
    def _ensure_project(conn: Any, tenant_id: str, project_id: str) -> None:
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
            raise StarletteHTTPException(404, detail={"code": "PROJECT_NOT_FOUND"})

    @staticmethod
    def _source_rows(conn: Any, tenant_id: str, project_id: str) -> list[Mapping[str, Any]]:
        return conn.execute(
            text(
                """
                SELECT LOWER(TRIM(TRAILING '.' FROM c.host)) AS normalized_host,
                       COUNT(*) AS citation_count,
                       COUNT(DISTINCT c.snapshot_id) AS sample_count,
                       COUNT(DISTINCT s.provider) AS provider_count,
                       MIN(c.created_at) AS first_seen_at,
                       MAX(c.created_at) AS last_seen_at
                FROM airank_source_citations c
                JOIN airank_answer_snapshots s
                  ON s.tenant_id=c.tenant_id AND s.id=c.snapshot_id
                WHERE c.tenant_id=:tenant_id AND c.project_id=:project_id
                  AND c.host IS NOT NULL AND TRIM(c.host)<>''
                GROUP BY LOWER(TRIM(TRAILING '.' FROM c.host))
                ORDER BY citation_count DESC, normalized_host ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()

    @staticmethod
    def _revision_rows(
        conn: Any, tenant_id: str, project_id: str
    ) -> list[Mapping[str, Any]]:
        return conn.execute(
            text(
                """
                SELECT * FROM airank_source_classification_revisions
                WHERE tenant_id=:tenant_id AND project_id=:project_id
                ORDER BY normalized_host ASC, revision_number DESC, reviewed_at DESC, id DESC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()

    def list(self, tenant_id: str, project_id: str) -> list[SourceRegistryEntryData]:
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            sources = self._source_rows(conn, tenant_id, project_id)
            revisions = self._revision_rows(conn, tenant_id, project_id)
        by_host: dict[str, list[SourceClassificationRevisionData]] = {}
        for row in revisions:
            revision = self._revision(row)
            by_host.setdefault(revision.normalized_host, []).append(revision)
        entries: list[SourceRegistryEntryData] = []
        for source in sources:
            raw_host = str(source["normalized_host"] or "")
            try:
                normalized_host = normalize_source_host(raw_host)
                reviewable = True
            except ValueError:
                normalized_host = raw_host
                reviewable = False
            history = by_host.get(normalized_host, [])
            current = history[0] if history else None
            entries.append(
                SourceRegistryEntryData(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    normalized_host=normalized_host,
                    reviewable=reviewable,
                    citation_count=int(source["citation_count"] or 0),
                    sample_count=int(source["sample_count"] or 0),
                    provider_count=int(source["provider_count"] or 0),
                    first_seen_at=as_utc(source["first_seen_at"]),
                    last_seen_at=as_utc(source["last_seen_at"]),
                    classification_status=(
                        current.classification_status if current else "unclassified"
                    ),
                    current_revision=current,
                    history=[],
                )
            )
        return entries

    def get(
        self, tenant_id: str, project_id: str, normalized_host: str
    ) -> SourceRegistryEntryData:
        entry = next(
            (
                item
                for item in self.list(tenant_id, project_id)
                if item.normalized_host == normalized_host
            ),
            None,
        )
        if entry is None:
            raise StarletteHTTPException(
                404, detail={"code": "SOURCE_REGISTRY_ENTRY_NOT_FOUND"}
            )
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM airank_source_classification_revisions
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND normalized_host=:normalized_host
                    ORDER BY revision_number DESC, reviewed_at DESC, id DESC
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "normalized_host": normalized_host,
                },
            ).mappings().all()
        history = [self._revision(row) for row in rows]
        return entry.model_copy(
            update={"history": history, "current_revision": history[0] if history else None}
        )

    def review(
        self,
        tenant_id: str,
        project_id: str,
        normalized_host: str,
        payload: SourceClassificationReviewRequest,
        idempotency_key: str,
        trace_id: str,
    ) -> SourceRegistryEntryData:
        request_sha256 = classification_request_sha256(
            tenant_id, project_id, normalized_host, payload
        )
        now = utc_now()
        now_db = now.replace(tzinfo=None)
        with self.engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            existing = conn.execute(
                text(
                    """
                    SELECT * FROM airank_source_classification_revisions
                    WHERE tenant_id=:tenant_id AND idempotency_key=:idempotency_key
                    FOR UPDATE
                    """
                ),
                {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
            ).mappings().first()
            if existing is not None:
                if (
                    str(existing["request_sha256"]) != request_sha256
                    or str(existing["project_id"]) != project_id
                    or str(existing["normalized_host"]) != normalized_host
                ):
                    raise StarletteHTTPException(
                        409, detail={"code": "IDEMPOTENCY_CONFLICT"}
                    )
                replay_revision = self._revision(existing, replay=True)
            else:
                source = conn.execute(
                    text(
                        """
                        SELECT c.id FROM airank_source_citations c
                        WHERE c.tenant_id=:tenant_id AND c.project_id=:project_id
                          AND LOWER(TRIM(TRAILING '.' FROM c.host))=:normalized_host
                        ORDER BY c.id LIMIT 1 FOR UPDATE
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "normalized_host": normalized_host,
                    },
                ).first()
                if source is None:
                    raise StarletteHTTPException(
                        404, detail={"code": "SOURCE_REGISTRY_ENTRY_NOT_FOUND"}
                    )
                current = conn.execute(
                    text(
                        """
                        SELECT * FROM airank_source_classification_revisions
                        WHERE tenant_id=:tenant_id AND project_id=:project_id
                          AND normalized_host=:normalized_host
                        ORDER BY revision_number DESC, reviewed_at DESC, id DESC
                        LIMIT 1 FOR UPDATE
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "normalized_host": normalized_host,
                    },
                ).mappings().first()
                expected = str(current["id"]) if current else None
                if payload.supersedes_revision_id != expected:
                    raise StarletteHTTPException(
                        409,
                        detail={
                            "code": "SOURCE_CLASSIFICATION_VERSION_CONFLICT",
                            "details": {"expected_revision_id": expected},
                        },
                    )
                revision_id = f"source_class_{uuid4().hex}"
                revision_number = int(current["revision_number"] or 0) + 1 if current else 1
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_source_classification_revisions (
                          id, tenant_id, project_id, normalized_host, revision_number,
                          source_category_l1, source_type, ecosystem,
                          classification_status, classification_method,
                          classification_confidence, authority_level, usage_policy,
                          risk_level, evidence_note, evidence_url,
                          source_dataset_name, source_dataset_version, valid_until,
                          reviewed_by, reviewed_at, supersedes_revision_id,
                          idempotency_key, request_sha256, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :normalized_host, :revision_number,
                          :source_category_l1, :source_type, :ecosystem,
                          'reviewed', 'human_review',
                          :classification_confidence, :authority_level, :usage_policy,
                          :risk_level, :evidence_note, :evidence_url,
                          NULL, NULL, :valid_until,
                          :reviewed_by, :reviewed_at, :supersedes_revision_id,
                          :idempotency_key, :request_sha256, :created_at
                        )
                        """
                    ),
                    {
                        "id": revision_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "normalized_host": normalized_host,
                        "revision_number": revision_number,
                        "source_category_l1": payload.source_category_l1,
                        "source_type": payload.source_type,
                        "ecosystem": payload.ecosystem,
                        "classification_confidence": payload.classification_confidence,
                        "authority_level": payload.authority_level,
                        "usage_policy": payload.usage_policy,
                        "risk_level": payload.risk_level,
                        "evidence_note": payload.evidence_note,
                        "evidence_url": payload.evidence_url,
                        "valid_until": (
                            as_utc(payload.valid_until).replace(tzinfo=None)
                            if payload.valid_until
                            else None
                        ),
                        "reviewed_by": payload.reviewed_by,
                        "reviewed_at": now_db,
                        "supersedes_revision_id": payload.supersedes_revision_id,
                        "idempotency_key": idempotency_key,
                        "request_sha256": request_sha256,
                        "created_at": now_db,
                    },
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_audit_events (
                          id, tenant_id, project_id, actor_user_id, event_type,
                          entity_type, entity_id, trace_id, payload_json, created_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :actor_user_id,
                          'source.classification_reviewed', 'source_classification',
                          :entity_id, :trace_id, :payload_json, :created_at
                        )
                        """
                    ),
                    {
                        "id": f"audit_{uuid4().hex}",
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "actor_user_id": payload.reviewed_by,
                        "entity_id": revision_id,
                        "trace_id": trace_id,
                        "payload_json": json.dumps(
                            {
                                "normalized_host": normalized_host,
                                "revision_number": revision_number,
                                "source_category_l1": payload.source_category_l1,
                                "source_type": payload.source_type,
                                "classification_status": "reviewed",
                                "classification_method": "human_review",
                                "classification_confidence": payload.classification_confidence,
                                "authority_level": payload.authority_level,
                                "usage_policy": payload.usage_policy,
                                "risk_level": payload.risk_level,
                                "request_sha256": request_sha256,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "created_at": now_db,
                    },
                )
                replay_revision = None
        entry = self.get(tenant_id, project_id, normalized_host)
        if replay_revision is not None:
            history = [
                item.model_copy(
                    update={
                        "idempotent_replay": item.revision_id
                        == replay_revision.revision_id
                    }
                )
                for item in entry.history
            ]
            return entry.model_copy(
                update={
                    "current_revision": history[0] if history else None,
                    "history": history,
                }
            )
        return entry


def build_repository() -> SourceRegistryRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    if database_url:
        return MySQLSourceRegistryRepository(database_url)
    return InMemorySourceRegistryRepository()


SOURCE_REGISTRY_REPOSITORY: SourceRegistryRepository = build_repository()


@router.get(
    "/projects/{project_id}/source-registry",
    response_model=SourceRegistryListResponse,
)
def list_source_registry(
    project_id: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> SourceRegistryListResponse:
    rows = SOURCE_REGISTRY_REPOSITORY.list(tenant_id, project_id)
    return SourceRegistryListResponse(
        data=rows,
        meta={
            **response_meta(trace_id),
            "total": len(rows),
            "classified_count": sum(
                row.classification_status != "unclassified" for row in rows
            ),
            "unclassified_count": sum(
                row.classification_status == "unclassified" for row in rows
            ),
            "classification_policy": "exact_host_human_review_only",
        },
    )


@router.get(
    "/projects/{project_id}/source-registry/{host}",
    response_model=SourceRegistryEntryResponse,
)
def get_source_registry_entry(
    project_id: str,
    host: str,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
) -> SourceRegistryEntryResponse:
    try:
        normalized_host = normalize_source_host(host)
    except ValueError as exc:
        raise StarletteHTTPException(
            422, detail={"code": "VALIDATION_FAILED", "details": {"reason": str(exc)}}
        ) from exc
    return SourceRegistryEntryResponse(
        data=SOURCE_REGISTRY_REPOSITORY.get(tenant_id, project_id, normalized_host),
        meta=response_meta(trace_id),
    )


@router.post(
    "/projects/{project_id}/source-registry/{host}/reviews",
    response_model=SourceRegistryEntryResponse,
    status_code=201,
)
def review_source_registry_entry(
    project_id: str,
    host: str,
    payload: SourceClassificationReviewRequest,
    tenant_id: str = Header(default="tenant_demo", alias="tenant-id"),
    trace_id: Optional[str] = Header(default=None, alias=TRACE_HEADER),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=160),
    authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"),
) -> SourceRegistryEntryResponse:
    try:
        normalized_host = normalize_source_host(host)
    except ValueError as exc:
        raise StarletteHTTPException(
            422, detail={"code": "VALIDATION_FAILED", "details": {"reason": str(exc)}}
        ) from exc
    trusted_payload = payload.model_copy(
        update={"reviewed_by": trusted_actor(payload.reviewed_by, authenticated_actor)}
    )
    effective_trace_id = trace_id or f"trc_{uuid4().hex[:16]}"
    return SourceRegistryEntryResponse(
        data=SOURCE_REGISTRY_REPOSITORY.review(
            tenant_id,
            project_id,
            normalized_host,
            trusted_payload,
            idempotency_key,
            effective_trace_id,
        ),
        meta=response_meta(effective_trace_id),
    )
