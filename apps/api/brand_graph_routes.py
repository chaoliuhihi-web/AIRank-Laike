from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import unicodedata
from typing import Any, Literal, Mapping, Optional, Protocol
from uuid import uuid4

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException


router = APIRouter(prefix="/api/v1", tags=["brand-graph"])

BRAND_GRAPH_CONTRACT_VERSION = "airank.brand-graph.v1"
BRAND_GRAPH_COMPILER_VERSION = "airank.brand-graph-compiler.v1"
ENTITY_ROLES = ("target", "competitor", "related")
ENTITY_KINDS = ("brand", "company", "product", "service")
USAGE_SCOPES = ("measurement_only", "public_and_measurement")
GRAPH_STATUSES = ("governed", "partial", "blocked", "legacy_unverified")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).replace(tzinfo=None)


def as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise TypeError(f"unsupported datetime {value!r}")


def json_value(value: object, default: object) -> object:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def normalize_entity_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return "".join(character for character in normalized if character.isalnum())


def response_meta(trace_id: Optional[str]) -> dict[str, str]:
    return {
        "trace_id": trace_id or f"trc_{uuid4().hex[:16]}",
        "request_id": f"req_{uuid4().hex[:16]}",
    }


def error(status_code: int, code: str, details: Mapping[str, object]) -> StarletteHTTPException:
    return StarletteHTTPException(status_code=status_code, detail={"code": code, "details": dict(details)})


def auth_enforcement_required() -> bool:
    return os.getenv("AIRANK_API_AUTH_ENFORCEMENT", "required").strip().lower() in {
        "1",
        "true",
        "yes",
        "required",
    }


def require_brand_graph_admin(permission_header: Optional[str]) -> None:
    if not auth_enforcement_required():
        return
    required = os.getenv("AIRANK_BRAND_GRAPH_ADMIN_PERMISSION", "airank:knowledge:admin").strip()
    granted = {item.strip() for item in (permission_header or "").split(",") if item.strip()}
    namespace = required.rsplit(":", 1)[0]
    if not granted.intersection({required, "*", "*:*:*", f"{namespace}:*"}):
        raise error(403, "AUTH_PERMISSION_FORBIDDEN", {"required_permission": required})


def trusted_actor(authenticated_actor: Optional[str]) -> str:
    actor = str(authenticated_actor or "").strip()
    if actor:
        return actor[:128]
    if not auth_enforcement_required():
        return "console-brand-graph"
    raise error(401, "AUTH_TOKEN_INVALID", {"reason": "authenticated_actor_required"})


class BrandEntityWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_role: Literal["target", "competitor", "related"]
    entity_kind: Literal["brand", "company", "product", "service"]
    canonical_name: str = Field(min_length=2, max_length=255)
    website_url: Optional[str] = Field(default=None, min_length=1, max_length=2048)
    external_ref_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    external_ref_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    usage_scope: Literal["measurement_only", "public_and_measurement"] = "measurement_only"
    fact_revision_id: str = Field(min_length=1, max_length=64)
    status: Literal["active", "disabled"] = "active"
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("canonical_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(normalize_entity_name(cleaned)) < 2:
            raise ValueError("canonical_name must contain at least two searchable characters")
        return cleaned


class BrandAliasWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias_text: str = Field(min_length=2, max_length=255)
    alias_type: Literal["official", "english", "abbreviation", "former_name", "misspelling", "product_variant"]
    language_code: Optional[str] = Field(default=None, min_length=2, max_length=16)
    usage_scope: Literal["measurement_only", "public_and_measurement"] = "measurement_only"
    fact_revision_id: str = Field(min_length=1, max_length=64)
    status: Literal["active", "disabled"] = "active"
    expected_version: Optional[int] = Field(default=None, ge=1)

    @field_validator("alias_text")
    @classmethod
    def valid_alias(cls, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(normalize_entity_name(cleaned)) < 2:
            raise ValueError("alias_text must contain at least two searchable characters")
        return cleaned


class BrandRelationWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_entity_id: str = Field(min_length=1, max_length=64)
    predicate: Literal["legal_name_of", "owns_product", "offers", "competitor_of", "former_name_of", "part_of"]
    object_entity_id: str = Field(min_length=1, max_length=64)
    usage_scope: Literal["measurement_only", "public_and_measurement"] = "measurement_only"
    fact_revision_id: str = Field(min_length=1, max_length=64)
    status: Literal["active", "disabled"] = "active"
    expected_version: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def relation_is_directional(self) -> "BrandRelationWriteRequest":
        if self.subject_entity_id == self.object_entity_id:
            raise ValueError("subject_entity_id and object_entity_id must differ")
        return self


class BrandGraphCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_by: str = Field(default="console-brand-graph", min_length=1, max_length=128)


class BrandEntityData(BaseModel):
    entity_id: str
    entity_role: Literal["target", "competitor", "related"]
    entity_kind: Literal["brand", "company", "product", "service"]
    canonical_name: str
    normalized_name: str
    website_url: Optional[str]
    external_ref_type: Optional[str]
    external_ref_id: Optional[str]
    usage_scope: Literal["measurement_only", "public_and_measurement"]
    fact_revision_id: str
    evidence_manifest_sha256: str
    status: Literal["active", "disabled"]
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class BrandAliasData(BaseModel):
    alias_id: str
    entity_id: str
    alias_text: str
    normalized_alias: str
    alias_type: Literal["official", "english", "abbreviation", "former_name", "misspelling", "product_variant"]
    language_code: Optional[str]
    usage_scope: Literal["measurement_only", "public_and_measurement"]
    fact_revision_id: str
    evidence_manifest_sha256: str
    status: Literal["active", "disabled"]
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class BrandRelationData(BaseModel):
    relation_id: str
    subject_entity_id: str
    predicate: Literal["legal_name_of", "owns_product", "offers", "competitor_of", "former_name_of", "part_of"]
    object_entity_id: str
    usage_scope: Literal["measurement_only", "public_and_measurement"]
    fact_revision_id: str
    evidence_manifest_sha256: str
    status: Literal["active", "disabled"]
    version: int
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class BrandGraphSnapshotData(BaseModel):
    snapshot_id: str
    tenant_id: str
    project_id: str
    contract_version: str
    compiler_version: str
    status: Literal["governed", "partial", "blocked", "legacy_unverified"]
    source_manifest_sha256: str
    graph_sha256: str
    graph: dict[str, Any]
    measurement_lexicon: dict[str, Any]
    public_jsonld: dict[str, Any]
    ambiguous_aliases: list[dict[str, Any]]
    known_limitations: list[str]
    created_by: str
    created_at: datetime


class BrandGraphPortfolioData(BaseModel):
    contract_version: str = BRAND_GRAPH_CONTRACT_VERSION
    project_id: str
    entities: list[BrandEntityData]
    aliases: list[BrandAliasData]
    relations: list[BrandRelationData]
    latest_snapshot: Optional[BrandGraphSnapshotData]
    measurement_ready: bool
    public_export_ready: bool
    known_limitations: list[str]


class BrandEntityResponse(BaseModel):
    data: BrandEntityData
    meta: dict[str, str]


class BrandAliasResponse(BaseModel):
    data: BrandAliasData
    meta: dict[str, str]


class BrandRelationResponse(BaseModel):
    data: BrandRelationData
    meta: dict[str, str]


class BrandGraphSnapshotResponse(BaseModel):
    data: BrandGraphSnapshotData
    meta: dict[str, str]


class BrandGraphPortfolioResponse(BaseModel):
    data: BrandGraphPortfolioData
    meta: dict[str, str]


def _entity_data(row: Mapping[str, Any]) -> BrandEntityData:
    return BrandEntityData(
        entity_id=str(row["id"]),
        entity_role=row["entity_role"],
        entity_kind=row["entity_kind"],
        canonical_name=str(row["canonical_name"]),
        normalized_name=str(row["normalized_name"]),
        website_url=row["website_url"],
        external_ref_type=row["external_ref_type"],
        external_ref_id=row["external_ref_id"],
        usage_scope=row["usage_scope"],
        fact_revision_id=str(row["fact_revision_id"]),
        evidence_manifest_sha256=str(row["evidence_manifest_sha256"]),
        status=row["status"],
        version=int(row["version"]),
        created_by=str(row["created_by"]),
        updated_by=str(row["updated_by"]),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


def _alias_data(row: Mapping[str, Any]) -> BrandAliasData:
    return BrandAliasData(
        alias_id=str(row["id"]),
        entity_id=str(row["entity_id"]),
        alias_text=str(row["alias_text"]),
        normalized_alias=str(row["normalized_alias"]),
        alias_type=row["alias_type"],
        language_code=row["language_code"],
        usage_scope=row["usage_scope"],
        fact_revision_id=str(row["fact_revision_id"]),
        evidence_manifest_sha256=str(row["evidence_manifest_sha256"]),
        status=row["status"],
        version=int(row["version"]),
        created_by=str(row["created_by"]),
        updated_by=str(row["updated_by"]),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


def _relation_data(row: Mapping[str, Any]) -> BrandRelationData:
    return BrandRelationData(
        relation_id=str(row["id"]),
        subject_entity_id=str(row["subject_entity_id"]),
        predicate=row["predicate"],
        object_entity_id=str(row["object_entity_id"]),
        usage_scope=row["usage_scope"],
        fact_revision_id=str(row["fact_revision_id"]),
        evidence_manifest_sha256=str(row["evidence_manifest_sha256"]),
        status=row["status"],
        version=int(row["version"]),
        created_by=str(row["created_by"]),
        updated_by=str(row["updated_by"]),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


def _snapshot_data(row: Mapping[str, Any]) -> BrandGraphSnapshotData:
    return BrandGraphSnapshotData(
        snapshot_id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        project_id=str(row["project_id"]),
        contract_version=str(row["contract_version"]),
        compiler_version=str(row["compiler_version"]),
        status=row["status"],
        source_manifest_sha256=str(row["source_manifest_sha256"]),
        graph_sha256=str(row["graph_sha256"]),
        graph=dict(json_value(row["graph_json"], {})),
        measurement_lexicon=dict(json_value(row["measurement_lexicon_json"], {})),
        public_jsonld=dict(json_value(row["public_jsonld_json"], {})),
        ambiguous_aliases=list(json_value(row["ambiguous_aliases_json"], [])),
        known_limitations=[str(item) for item in list(json_value(row["known_limitations_json"], []))],
        created_by=str(row["created_by"]),
        created_at=as_utc(row["created_at"]),
    )


def _brand_graph_fact_semantic_reasons(row: Mapping[str, Any]) -> list[str]:
    """Keep measurement entities bound to explicit identity evidence."""
    reasons: list[str] = []
    if str(row.get("fact_type") or "") != "brand_identity":
        reasons.append("fact_type_not_brand_identity")
    if str(row.get("subject_type") or "general") == "general" or not row.get("subject_ref_id"):
        reasons.append("fact_subject_not_entity_bound")
    return reasons


def _eligible_fact_evidence(
    conn: Any,
    tenant_id: str,
    project_id: str,
    revision_id: str,
    usage_scope: str,
    at: datetime,
) -> dict[str, Any]:
    row = conn.execute(
        text(
            """
            SELECT r.id, r.fact_atom_id, r.revision_number, r.content_sha256,
                   r.status AS revision_status, r.source_ids_json,
                   r.valid_from AS revision_valid_from, r.valid_until AS revision_valid_until,
                   f.current_revision_id, f.status AS fact_status, f.fact_type,
                   f.subject_type, f.subject_ref_id, f.disclosure,
                   f.risk_level, f.valid_until AS fact_valid_until,
                   (SELECT COUNT(*) FROM airank_fact_conflicts c
                    WHERE c.tenant_id=r.tenant_id AND c.project_id=r.project_id
                      AND c.fact_atom_id=r.fact_atom_id AND c.status='open') AS open_conflict_count
            FROM airank_fact_revisions r
            JOIN airank_fact_atoms f ON f.id=r.fact_atom_id
            WHERE r.tenant_id=:tenant_id AND r.project_id=:project_id AND r.id=:revision_id
              AND f.tenant_id=:tenant_id AND f.project_id=:project_id AND f.deleted_at IS NULL
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id, "revision_id": revision_id},
    ).mappings().first()
    if row is None:
        raise error(404, "FACT_REVISION_NOT_FOUND", {"revision_id": revision_id})

    reasons: list[str] = []
    reasons.extend(_brand_graph_fact_semantic_reasons(row))
    if row["revision_status"] != "approved" or row["fact_status"] != "confirmed":
        reasons.append("fact_revision_not_approved")
    if row["current_revision_id"] != revision_id:
        reasons.append("fact_revision_not_current")
    if int(row["open_conflict_count"] or 0) > 0:
        reasons.append("fact_has_open_conflict")
    disclosure = str(row["disclosure"] or "pending_approval")
    allowed_disclosures = {"public", "redacted"} if usage_scope == "public_and_measurement" else {"public", "redacted", "internal"}
    if disclosure not in allowed_disclosures:
        reasons.append("fact_disclosure_not_allowed")
    at_db = database_datetime(at)
    if row["revision_valid_from"] is not None and row["revision_valid_from"] > at_db:
        reasons.append("fact_revision_not_yet_valid")
    if row["revision_valid_until"] is not None and row["revision_valid_until"] <= at_db:
        reasons.append("fact_revision_expired")
    if row["fact_valid_until"] is not None and row["fact_valid_until"] <= at_db:
        reasons.append("fact_expired")

    source_ids = [str(item) for item in list(json_value(row["source_ids_json"], []))]
    if not source_ids:
        reasons.append("fact_source_required")
        source_rows: list[Mapping[str, Any]] = []
    else:
        placeholders = ",".join(f":source_{index}" for index in range(len(source_ids)))
        params: dict[str, Any] = {"tenant_id": tenant_id, "project_id": project_id, "at": at_db}
        params.update({f"source_{index}": source_id for index, source_id in enumerate(source_ids)})
        source_rows = list(
            conn.execute(
                text(
                    f"""
                    SELECT id, content_sha256, source_uri, authority_level, risk_level,
                           status, valid_from, valid_until
                    FROM airank_knowledge_sources
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND id IN ({placeholders})
                    ORDER BY id ASC
                    """
                ),
                params,
            ).mappings().all()
        )
        if len(source_rows) != len(set(source_ids)):
            reasons.append("fact_source_missing")
        for source in source_rows:
            if source["status"] != "active":
                reasons.append("fact_source_inactive")
            if source["valid_from"] is not None and source["valid_from"] > at_db:
                reasons.append("fact_source_not_yet_valid")
            if source["valid_until"] is not None and source["valid_until"] <= at_db:
                reasons.append("fact_source_expired")

    if reasons:
        raise error(
            409,
            "BRAND_GRAPH_FACT_NOT_ELIGIBLE",
            {"revision_id": revision_id, "reason_codes": sorted(set(reasons))},
        )

    return {
        "fact_revision_id": revision_id,
        "fact_atom_id": str(row["fact_atom_id"]),
        "revision_number": int(row["revision_number"]),
        "fact_revision_sha256": str(row["content_sha256"]),
        "fact_type": str(row["fact_type"]),
        "subject_type": str(row["subject_type"]),
        "subject_ref_id": str(row["subject_ref_id"]),
        "disclosure": disclosure,
        "risk_level": str(row["risk_level"]),
        "sources": [
            {
                "knowledge_source_id": str(source["id"]),
                "source_content_sha256": str(source["content_sha256"]),
                "authority_level": str(source["authority_level"]),
                "risk_level": str(source["risk_level"]),
            }
            for source in source_rows
        ],
    }


def _append_event(
    conn: Any,
    *,
    tenant_id: str,
    project_id: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    aggregate_version: int,
    request_sha256: str,
    actor: str,
    trace_id: str,
    payload: Mapping[str, Any],
    created_at: datetime,
) -> None:
    previous = conn.execute(
        text(
            """
            SELECT event_sha256 FROM airank_brand_graph_events
            WHERE tenant_id=:tenant_id AND aggregate_type=:aggregate_type
              AND aggregate_id=:aggregate_id
            ORDER BY aggregate_version DESC LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "aggregate_type": aggregate_type, "aggregate_id": aggregate_id},
    ).scalar()
    material = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "aggregate_version": aggregate_version,
        "request_sha256": request_sha256,
        "previous_event_sha256": previous,
        "actor_user_id": actor,
        "trace_id": trace_id,
        "payload": dict(payload),
        "created_at": created_at.isoformat(),
    }
    event_sha256 = canonical_sha256(material)
    conn.execute(
        text(
            """
            INSERT INTO airank_brand_graph_events (
              id, tenant_id, project_id, aggregate_type, aggregate_id, event_type,
              aggregate_version, request_sha256, previous_event_sha256,
              event_sha256, actor_user_id, trace_id, payload_json, created_at
            ) VALUES (
              :id, :tenant_id, :project_id, :aggregate_type, :aggregate_id, :event_type,
              :aggregate_version, :request_sha256, :previous_event_sha256,
              :event_sha256, :actor_user_id, :trace_id, :payload_json, :created_at
            )
            """
        ),
        {
            "id": stable_id("brand_event", aggregate_id, str(aggregate_version), event_sha256),
            "tenant_id": tenant_id,
            "project_id": project_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "aggregate_version": aggregate_version,
            "request_sha256": request_sha256,
            "previous_event_sha256": previous,
            "event_sha256": event_sha256,
            "actor_user_id": actor,
            "trace_id": trace_id,
            "payload_json": canonical_json(payload),
            "created_at": database_datetime(created_at),
        },
    )


def _legacy_graph_material(conn: Any, tenant_id: str, project_id: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    project = conn.execute(
        text(
            """
            SELECT id, brand_name, name, website_url, industry,
                   products_services_json, updated_at
            FROM airank_projects
            WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id},
    ).mappings().first()
    if project is None:
        raise error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})
    competitors = conn.execute(
        text(
            """
            SELECT id, name, website_url, metadata_json, updated_at
            FROM airank_competitors
            WHERE tenant_id=:tenant_id AND project_id=:project_id AND deleted_at IS NULL
            ORDER BY id ASC
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id},
    ).mappings().all()
    products = [str(item) for item in list(json_value(project["products_services_json"], [])) if str(item).strip()]
    target = {
        "entity_id": None,
        "canonical_name": str(project["brand_name"] or project["name"]),
        "brand_aliases": [],
        "company_names": [str(project["name"])] if project["name"] else [],
        "product_names": products,
        "website_url": str(project["website_url"] or ""),
    }
    competitor_items = [
        {"entity_id": str(row["id"]), "canonical_name": str(row["name"]), "aliases": []}
        for row in competitors
        if str(row["name"] or "").strip()
    ]
    source_manifest = {
        "mode": "legacy_project_fields",
        "project": {
            "id": str(project["id"]),
            "brand_name": project["brand_name"],
            "company_name": project["name"],
            "website_url": project["website_url"],
            "industry": project["industry"],
            "products": products,
            "updated_at": str(project["updated_at"]),
        },
        "competitors": [
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "website_url": row["website_url"],
                "metadata": json_value(row["metadata_json"], {}),
                "updated_at": str(row["updated_at"]),
            }
            for row in competitors
        ],
    }
    measurement_lexicon = {"target": target, "competitors": competitor_items}
    limitations = [
        "legacy_project_fields_are_not_bound_to_approved_fact_revisions",
        "legacy_alias_coverage_is_unknown",
        "public_jsonld_export_is_disabled",
    ]
    return source_manifest, measurement_lexicon, limitations


def compile_or_reuse_brand_graph_snapshot(
    conn: Any,
    tenant_id: str,
    project_id: str,
    *,
    created_by: str,
    created_at: Optional[datetime] = None,
) -> BrandGraphSnapshotData:
    now = created_at or utc_now()
    entity_rows = list(
        conn.execute(
            text(
                """
                SELECT * FROM airank_brand_entities
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active'
                ORDER BY entity_role ASC, entity_kind ASC, normalized_name ASC, id ASC
                """
            ),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).mappings().all()
    )

    if not entity_rows:
        source_manifest, measurement_lexicon, limitations = _legacy_graph_material(conn, tenant_id, project_id)
        status = "legacy_unverified"
        graph = {"entities": [], "aliases": [], "relations": [], "mode": "legacy_project_fields"}
        public_jsonld: dict[str, Any] = {}
        ambiguous: list[dict[str, Any]] = []
    else:
        alias_rows = list(
            conn.execute(
                text(
                    """
                    SELECT * FROM airank_brand_entity_aliases
                    WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active'
                    ORDER BY normalized_alias ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )
        relation_rows = list(
            conn.execute(
                text(
                    """
                    SELECT * FROM airank_brand_relations
                    WHERE tenant_id=:tenant_id AND project_id=:project_id AND status='active'
                    ORDER BY subject_entity_id ASC, predicate ASC, object_entity_id ASC, id ASC
                    """
                ),
                {"tenant_id": tenant_id, "project_id": project_id},
            ).mappings().all()
        )
        accepted_entities: list[dict[str, Any]] = []
        accepted_aliases: list[dict[str, Any]] = []
        accepted_relations: list[dict[str, Any]] = []
        invalid_records: list[dict[str, str]] = []

        def accept_with_current_evidence(row: Mapping[str, Any], record_type: str) -> Optional[dict[str, Any]]:
            try:
                evidence = _eligible_fact_evidence(
                    conn,
                    tenant_id,
                    project_id,
                    str(row["fact_revision_id"]),
                    str(row["usage_scope"]),
                    now,
                )
            except StarletteHTTPException as exc:
                details = exc.detail.get("details", {}) if isinstance(exc.detail, dict) else {}
                invalid_records.append(
                    {
                        "record_type": record_type,
                        "record_id": str(row["id"]),
                        "reason": ",".join(details.get("reason_codes", [exc.detail.get("code", "ineligible")]))
                        if isinstance(details, dict)
                        else "ineligible",
                    }
                )
                return None
            result = dict(row)
            result["evidence"] = evidence
            return result

        for row in entity_rows:
            accepted = accept_with_current_evidence(row, "entity")
            if accepted is not None:
                accepted_entities.append(accepted)
        accepted_entity_ids = {str(row["id"]) for row in accepted_entities}
        for row in alias_rows:
            if str(row["entity_id"]) not in accepted_entity_ids:
                invalid_records.append({"record_type": "alias", "record_id": str(row["id"]), "reason": "entity_ineligible"})
                continue
            accepted = accept_with_current_evidence(row, "alias")
            if accepted is not None:
                accepted_aliases.append(accepted)
        for row in relation_rows:
            if str(row["subject_entity_id"]) not in accepted_entity_ids or str(row["object_entity_id"]) not in accepted_entity_ids:
                invalid_records.append({"record_type": "relation", "record_id": str(row["id"]), "reason": "entity_ineligible"})
                continue
            accepted = accept_with_current_evidence(row, "relation")
            if accepted is not None:
                accepted_relations.append(accepted)

        token_owners: dict[str, set[str]] = defaultdict(set)
        token_text: dict[str, set[str]] = defaultdict(set)
        for row in accepted_entities:
            token_owners[str(row["normalized_name"])].add(str(row["id"]))
            token_text[str(row["normalized_name"])].add(str(row["canonical_name"]))
        for row in accepted_aliases:
            token_owners[str(row["normalized_alias"])].add(str(row["entity_id"]))
            token_text[str(row["normalized_alias"])].add(str(row["alias_text"]))
        ambiguous_keys = {key for key, owners in token_owners.items() if len(owners) > 1}
        ambiguous = [
            {
                "normalized_value": key,
                "observed_values": sorted(token_text[key]),
                "entity_ids": sorted(token_owners[key]),
                "excluded_from_measurement": True,
            }
            for key in sorted(ambiguous_keys)
        ]

        aliases_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in accepted_aliases:
            if str(row["normalized_alias"]) not in ambiguous_keys:
                aliases_by_entity[str(row["entity_id"])].append(row)

        target_brand_rows = [
            row for row in accepted_entities if row["entity_role"] == "target" and row["entity_kind"] == "brand"
        ]
        target_brand = target_brand_rows[0] if len(target_brand_rows) == 1 else None
        target_canonical_ambiguous = bool(
            target_brand is not None and str(target_brand["normalized_name"]) in ambiguous_keys
        )
        target_entity_rows = [row for row in accepted_entities if row["entity_role"] == "target"]
        brand_aliases = [
            str(alias["alias_text"])
            for row in target_entity_rows
            if row["entity_kind"] == "brand"
            for alias in aliases_by_entity[str(row["id"])]
        ]
        company_names = [
            value
            for row in target_entity_rows
            if row["entity_kind"] == "company"
            for value in [str(row["canonical_name"]), *[str(alias["alias_text"]) for alias in aliases_by_entity[str(row["id"])]]]
            if normalize_entity_name(value) not in ambiguous_keys
        ]
        product_names = [
            value
            for row in target_entity_rows
            if row["entity_kind"] in {"product", "service"}
            for value in [str(row["canonical_name"]), *[str(alias["alias_text"]) for alias in aliases_by_entity[str(row["id"])]]]
            if normalize_entity_name(value) not in ambiguous_keys
        ]
        competitor_items = [
            {
                "entity_id": str(row["id"]),
                "canonical_name": str(row["canonical_name"]),
                "aliases": [str(alias["alias_text"]) for alias in aliases_by_entity[str(row["id"])]],
            }
            for row in accepted_entities
            if row["entity_role"] == "competitor" and row["entity_kind"] in {"brand", "company", "product", "service"}
            and str(row["normalized_name"]) not in ambiguous_keys
        ]
        measurement_lexicon = {
            "target": {
                "entity_id": str(target_brand["id"]) if target_brand else None,
                "canonical_name": str(target_brand["canonical_name"]) if target_brand else "",
                "brand_aliases": sorted(set(brand_aliases)),
                "company_names": sorted(set(company_names)),
                "product_names": sorted(set(product_names)),
                "website_url": str(target_brand["website_url"] or "") if target_brand else "",
            },
            "competitors": competitor_items,
        }

        graph_entities = [
            {
                "entity_id": str(row["id"]),
                "entity_role": str(row["entity_role"]),
                "entity_kind": str(row["entity_kind"]),
                "canonical_name": str(row["canonical_name"]),
                "normalized_name": str(row["normalized_name"]),
                "website_url": row["website_url"],
                "usage_scope": str(row["usage_scope"]),
                "fact_revision_id": str(row["fact_revision_id"]),
                "evidence": row["evidence"],
                "version": int(row["version"]),
            }
            for row in accepted_entities
        ]
        graph_aliases = [
            {
                "alias_id": str(row["id"]),
                "entity_id": str(row["entity_id"]),
                "alias_text": str(row["alias_text"]),
                "normalized_alias": str(row["normalized_alias"]),
                "alias_type": str(row["alias_type"]),
                "usage_scope": str(row["usage_scope"]),
                "fact_revision_id": str(row["fact_revision_id"]),
                "evidence": row["evidence"],
                "version": int(row["version"]),
                "ambiguous": str(row["normalized_alias"]) in ambiguous_keys,
            }
            for row in accepted_aliases
        ]
        graph_relations = [
            {
                "relation_id": str(row["id"]),
                "subject_entity_id": str(row["subject_entity_id"]),
                "predicate": str(row["predicate"]),
                "object_entity_id": str(row["object_entity_id"]),
                "usage_scope": str(row["usage_scope"]),
                "fact_revision_id": str(row["fact_revision_id"]),
                "evidence": row["evidence"],
                "version": int(row["version"]),
            }
            for row in accepted_relations
        ]
        graph = {"mode": "governed", "entities": graph_entities, "aliases": graph_aliases, "relations": graph_relations}
        source_manifest = {
            "mode": "governed",
            "entity_versions": [{"id": item["entity_id"], "version": item["version"], "fact_revision_id": item["fact_revision_id"]} for item in graph_entities],
            "alias_versions": [{"id": item["alias_id"], "version": item["version"], "fact_revision_id": item["fact_revision_id"]} for item in graph_aliases],
            "relation_versions": [{"id": item["relation_id"], "version": item["version"], "fact_revision_id": item["fact_revision_id"]} for item in graph_relations],
            "invalid_records": invalid_records,
        }
        limitations = []
        if len(target_brand_rows) != 1:
            limitations.append("exactly_one_eligible_target_brand_is_required")
        if target_canonical_ambiguous:
            limitations.append("target_canonical_name_is_ambiguous")
        if ambiguous:
            limitations.append("ambiguous_aliases_were_excluded_from_measurement")
        if invalid_records:
            limitations.append("records_with_stale_or_ineligible_evidence_were_excluded")

        if len(target_brand_rows) != 1 or target_canonical_ambiguous:
            status = "blocked"
        elif ambiguous or invalid_records:
            status = "partial"
        else:
            status = "governed"

        public_nodes: list[dict[str, Any]] = []
        for entity in graph_entities:
            if entity["usage_scope"] != "public_and_measurement" or entity["evidence"]["disclosure"] not in {"public", "redacted"}:
                continue
            node: dict[str, Any] = {
                "@id": f"urn:airank:brand-entity:{entity['entity_id']}",
                "@type": {
                    "brand": "Brand",
                    "company": "Organization",
                    "product": "Product",
                    "service": "Service",
                }[entity["entity_kind"]],
                "name": entity["canonical_name"],
            }
            public_aliases = [
                alias["alias_text"]
                for alias in graph_aliases
                if alias["entity_id"] == entity["entity_id"]
                and not alias["ambiguous"]
                and alias["usage_scope"] == "public_and_measurement"
                and alias["evidence"]["disclosure"] in {"public", "redacted"}
            ]
            if public_aliases:
                node["alternateName"] = sorted(set(public_aliases))
            if entity["website_url"]:
                node["url"] = entity["website_url"]
            public_nodes.append(node)
        public_node_by_entity_id = {
            str(node["@id"]).removeprefix("urn:airank:brand-entity:"): node
            for node in public_nodes
        }
        for relation in graph_relations:
            if relation["usage_scope"] != "public_and_measurement" or relation["evidence"]["disclosure"] not in {"public", "redacted"}:
                continue
            if relation["subject_entity_id"] not in public_node_by_entity_id or relation["object_entity_id"] not in public_node_by_entity_id:
                continue
            subject = public_node_by_entity_id[relation["subject_entity_id"]]
            subject.setdefault(f"airank:{relation['predicate']}", []).append(
                {"@id": f"urn:airank:brand-entity:{relation['object_entity_id']}"}
            )
        public_jsonld = (
            {"@context": {"@vocab": "https://schema.org/", "airank": "https://airank.local/vocab/"}, "@graph": public_nodes}
            if public_nodes
            else {}
        )

    source_manifest_sha256 = canonical_sha256(source_manifest)
    snapshot_material = {
        "contract_version": BRAND_GRAPH_CONTRACT_VERSION,
        "compiler_version": BRAND_GRAPH_COMPILER_VERSION,
        "status": status,
        "source_manifest_sha256": source_manifest_sha256,
        "graph": graph,
        "measurement_lexicon": measurement_lexicon,
        "public_jsonld": public_jsonld,
        "ambiguous_aliases": ambiguous,
        "known_limitations": limitations,
    }
    graph_sha256 = canonical_sha256(snapshot_material)
    snapshot_id = stable_id("brand_graph", tenant_id, project_id, graph_sha256)
    conn.execute(
        text(
            """
            INSERT INTO airank_brand_graph_snapshots (
              id, tenant_id, project_id, contract_version, compiler_version, status,
              source_manifest_json, source_manifest_sha256, graph_json, graph_sha256,
              measurement_lexicon_json, public_jsonld_json, ambiguous_aliases_json,
              known_limitations_json, created_by, created_at
            )
            SELECT :id, :tenant_id, :project_id, :contract_version, :compiler_version, :status,
                   :source_manifest_json, :source_manifest_sha256, :graph_json, :graph_sha256,
                   :measurement_lexicon_json, :public_jsonld_json, :ambiguous_aliases_json,
                   :known_limitations_json, :created_by, :created_at
            WHERE NOT EXISTS (
              SELECT 1 FROM airank_brand_graph_snapshots
              WHERE tenant_id=:tenant_id AND project_id=:project_id AND graph_sha256=:graph_sha256
            )
            """
        ),
        {
            "id": snapshot_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "contract_version": BRAND_GRAPH_CONTRACT_VERSION,
            "compiler_version": BRAND_GRAPH_COMPILER_VERSION,
            "status": status,
            "source_manifest_json": canonical_json(source_manifest),
            "source_manifest_sha256": source_manifest_sha256,
            "graph_json": canonical_json(graph),
            "graph_sha256": graph_sha256,
            "measurement_lexicon_json": canonical_json(measurement_lexicon),
            "public_jsonld_json": canonical_json(public_jsonld),
            "ambiguous_aliases_json": canonical_json(ambiguous),
            "known_limitations_json": canonical_json(limitations),
            "created_by": created_by,
            "created_at": database_datetime(now),
        },
    )
    row = conn.execute(
        text(
            """
            SELECT * FROM airank_brand_graph_snapshots
            WHERE tenant_id=:tenant_id AND project_id=:project_id AND graph_sha256=:graph_sha256
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id, "graph_sha256": graph_sha256},
    ).mappings().one()
    return _snapshot_data(row)


def load_brand_graph_snapshot(conn: Any, tenant_id: str, project_id: str, snapshot_id: str) -> BrandGraphSnapshotData:
    row = conn.execute(
        text(
            """
            SELECT * FROM airank_brand_graph_snapshots
            WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:snapshot_id
            """
        ),
        {"tenant_id": tenant_id, "project_id": project_id, "snapshot_id": snapshot_id},
    ).mappings().first()
    if row is None:
        raise error(404, "BRAND_GRAPH_SNAPSHOT_NOT_FOUND", {"snapshot_id": snapshot_id})
    return _snapshot_data(row)


class BrandGraphRepository(Protocol):
    def create_entity(self, tenant_id: str, project_id: str, payload: BrandEntityWriteRequest, actor: str, trace_id: str) -> BrandEntityData: ...
    def update_entity(self, tenant_id: str, project_id: str, entity_id: str, payload: BrandEntityWriteRequest, actor: str, trace_id: str) -> BrandEntityData: ...
    def create_alias(self, tenant_id: str, project_id: str, entity_id: str, payload: BrandAliasWriteRequest, actor: str, trace_id: str) -> BrandAliasData: ...
    def update_alias(self, tenant_id: str, project_id: str, alias_id: str, payload: BrandAliasWriteRequest, actor: str, trace_id: str) -> BrandAliasData: ...
    def create_relation(self, tenant_id: str, project_id: str, payload: BrandRelationWriteRequest, actor: str, trace_id: str) -> BrandRelationData: ...
    def update_relation(self, tenant_id: str, project_id: str, relation_id: str, payload: BrandRelationWriteRequest, actor: str, trace_id: str) -> BrandRelationData: ...
    def compile_snapshot(self, tenant_id: str, project_id: str, actor: str) -> BrandGraphSnapshotData: ...
    def get_snapshot(self, tenant_id: str, snapshot_id: str) -> BrandGraphSnapshotData: ...
    def portfolio(self, tenant_id: str, project_id: str) -> BrandGraphPortfolioData: ...


class InMemoryBrandGraphRepository:
    """Dev-only repository: never emits governed snapshots without the MySQL fact store."""

    def _blocked(self, *_args: Any, **_kwargs: Any) -> Any:
        raise error(503, "INTEGRATION_CAPABILITY_BLOCKED", {"capability": "mysql_brand_graph"})

    create_entity = _blocked
    update_entity = _blocked
    create_alias = _blocked
    update_alias = _blocked
    create_relation = _blocked
    update_relation = _blocked
    compile_snapshot = _blocked
    get_snapshot = _blocked
    portfolio = _blocked


class MySQLBrandGraphRepository:
    def __init__(self, database_url: str) -> None:
        if database_url.startswith("sqlite") and ":memory:" in database_url:
            self._engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self._engine = create_engine(database_url, pool_pre_ping=True)

    def _ensure_project(self, conn: Any, tenant_id: str, project_id: str) -> None:
        found = conn.execute(
            text("SELECT id FROM airank_projects WHERE tenant_id=:tenant_id AND id=:project_id AND deleted_at IS NULL"),
            {"tenant_id": tenant_id, "project_id": project_id},
        ).scalar()
        if found is None:
            raise error(404, "PROJECT_NOT_FOUND", {"project_id": project_id})

    def _entity_row(self, conn: Any, tenant_id: str, project_id: str, entity_id: str) -> Mapping[str, Any]:
        row = conn.execute(
            text("SELECT * FROM airank_brand_entities WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:entity_id"),
            {"tenant_id": tenant_id, "project_id": project_id, "entity_id": entity_id},
        ).mappings().first()
        if row is None:
            raise error(404, "BRAND_ENTITY_NOT_FOUND", {"entity_id": entity_id})
        return row

    def create_entity(self, tenant_id: str, project_id: str, payload: BrandEntityWriteRequest, actor: str, trace_id: str) -> BrandEntityData:
        if payload.expected_version is not None:
            raise error(409, "EXPECTED_VERSION_NOT_ALLOWED_ON_CREATE", {"expected_version": payload.expected_version})
        now = utc_now()
        normalized_name = normalize_entity_name(payload.canonical_name)
        entity_id = f"brand_entity_{uuid4().hex[:16]}"
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            evidence = _eligible_fact_evidence(conn, tenant_id, project_id, payload.fact_revision_id, payload.usage_scope, now)
            request_material = {**payload.model_dump(mode="json", exclude={"expected_version"}), "normalized_name": normalized_name, "evidence": evidence}
            request_sha256 = canonical_sha256(request_material)
            try:
                conn.execute(text("""
                    INSERT INTO airank_brand_entities (
                      id, tenant_id, project_id, entity_role, entity_kind, canonical_name,
                      normalized_name, website_url, external_ref_type, external_ref_id,
                      usage_scope, fact_revision_id, evidence_manifest_json,
                      evidence_manifest_sha256, status, request_sha256, version,
                      created_by, updated_by, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :entity_role, :entity_kind, :canonical_name,
                      :normalized_name, :website_url, :external_ref_type, :external_ref_id,
                      :usage_scope, :fact_revision_id, :evidence_manifest_json,
                      :evidence_manifest_sha256, :status, :request_sha256, 1,
                      :actor, :actor, :created_at, :created_at
                    )
                """), {
                    "id": entity_id, "tenant_id": tenant_id, "project_id": project_id,
                    "entity_role": payload.entity_role, "entity_kind": payload.entity_kind,
                    "canonical_name": payload.canonical_name, "normalized_name": normalized_name,
                    "website_url": payload.website_url, "external_ref_type": payload.external_ref_type,
                    "external_ref_id": payload.external_ref_id, "usage_scope": payload.usage_scope,
                    "fact_revision_id": payload.fact_revision_id,
                    "evidence_manifest_json": canonical_json(evidence),
                    "evidence_manifest_sha256": canonical_sha256(evidence), "status": payload.status,
                    "request_sha256": request_sha256, "actor": actor, "created_at": database_datetime(now),
                })
            except Exception as exc:
                if "Duplicate" in str(exc) or "UNIQUE constraint" in str(exc):
                    raise error(409, "BRAND_ENTITY_DUPLICATE", {"normalized_name": normalized_name}) from exc
                raise
            _append_event(conn, tenant_id=tenant_id, project_id=project_id, aggregate_type="entity", aggregate_id=entity_id, event_type="brand_entity_created", aggregate_version=1, request_sha256=request_sha256, actor=actor, trace_id=trace_id, payload=request_material, created_at=now)
            row = self._entity_row(conn, tenant_id, project_id, entity_id)
        return _entity_data(row)

    def update_entity(self, tenant_id: str, project_id: str, entity_id: str, payload: BrandEntityWriteRequest, actor: str, trace_id: str) -> BrandEntityData:
        if payload.expected_version is None:
            raise error(409, "EXPECTED_VERSION_REQUIRED", {"entity_id": entity_id})
        now = utc_now()
        with self._engine.begin() as conn:
            current = self._entity_row(conn, tenant_id, project_id, entity_id)
            if int(current["version"]) != payload.expected_version:
                raise error(409, "STATE_VERSION_CONFLICT", {"expected_version": payload.expected_version, "actual_version": int(current["version"])})
            evidence = _eligible_fact_evidence(conn, tenant_id, project_id, payload.fact_revision_id, payload.usage_scope, now)
            normalized_name = normalize_entity_name(payload.canonical_name)
            version = payload.expected_version + 1
            material = {**payload.model_dump(mode="json", exclude={"expected_version"}), "normalized_name": normalized_name, "evidence": evidence}
            request_sha256 = canonical_sha256(material)
            conn.execute(text("""
                UPDATE airank_brand_entities SET entity_role=:entity_role, entity_kind=:entity_kind,
                  canonical_name=:canonical_name, normalized_name=:normalized_name, website_url=:website_url,
                  external_ref_type=:external_ref_type, external_ref_id=:external_ref_id,
                  usage_scope=:usage_scope, fact_revision_id=:fact_revision_id,
                  evidence_manifest_json=:evidence_manifest_json,
                  evidence_manifest_sha256=:evidence_manifest_sha256, status=:status,
                  request_sha256=:request_sha256, version=:version, updated_by=:actor, updated_at=:updated_at
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:entity_id
            """), {
                "tenant_id": tenant_id, "project_id": project_id, "entity_id": entity_id,
                "entity_role": payload.entity_role, "entity_kind": payload.entity_kind,
                "canonical_name": payload.canonical_name, "normalized_name": normalized_name,
                "website_url": payload.website_url, "external_ref_type": payload.external_ref_type,
                "external_ref_id": payload.external_ref_id, "usage_scope": payload.usage_scope,
                "fact_revision_id": payload.fact_revision_id,
                "evidence_manifest_json": canonical_json(evidence), "evidence_manifest_sha256": canonical_sha256(evidence),
                "status": payload.status, "request_sha256": request_sha256,
                "version": version, "actor": actor, "updated_at": database_datetime(now),
            })
            _append_event(conn, tenant_id=tenant_id, project_id=project_id, aggregate_type="entity", aggregate_id=entity_id, event_type="brand_entity_updated", aggregate_version=version, request_sha256=request_sha256, actor=actor, trace_id=trace_id, payload=material, created_at=now)
            row = self._entity_row(conn, tenant_id, project_id, entity_id)
        return _entity_data(row)

    def create_alias(self, tenant_id: str, project_id: str, entity_id: str, payload: BrandAliasWriteRequest, actor: str, trace_id: str) -> BrandAliasData:
        if payload.expected_version is not None:
            raise error(409, "EXPECTED_VERSION_NOT_ALLOWED_ON_CREATE", {"expected_version": payload.expected_version})
        now = utc_now()
        alias_id = f"brand_alias_{uuid4().hex[:16]}"
        normalized_alias = normalize_entity_name(payload.alias_text)
        with self._engine.begin() as conn:
            entity = self._entity_row(conn, tenant_id, project_id, entity_id)
            if normalized_alias == str(entity["normalized_name"]):
                raise error(409, "BRAND_ALIAS_REDUNDANT", {"entity_id": entity_id, "normalized_alias": normalized_alias})
            evidence = _eligible_fact_evidence(conn, tenant_id, project_id, payload.fact_revision_id, payload.usage_scope, now)
            material = {**payload.model_dump(mode="json", exclude={"expected_version"}), "entity_id": entity_id, "normalized_alias": normalized_alias, "evidence": evidence}
            request_sha256 = canonical_sha256(material)
            try:
                conn.execute(text("""
                    INSERT INTO airank_brand_entity_aliases (
                      id, tenant_id, project_id, entity_id, alias_text, normalized_alias,
                      alias_type, language_code, usage_scope, fact_revision_id,
                      evidence_manifest_json, evidence_manifest_sha256, status,
                      request_sha256, version, created_by, updated_by, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :entity_id, :alias_text, :normalized_alias,
                      :alias_type, :language_code, :usage_scope, :fact_revision_id,
                      :evidence_manifest_json, :evidence_manifest_sha256, :status,
                      :request_sha256, 1, :actor, :actor, :created_at, :created_at
                    )
                """), {
                    "id": alias_id, "tenant_id": tenant_id, "project_id": project_id, "entity_id": entity_id,
                    "alias_text": payload.alias_text, "normalized_alias": normalized_alias, "alias_type": payload.alias_type,
                    "language_code": payload.language_code, "usage_scope": payload.usage_scope,
                    "fact_revision_id": payload.fact_revision_id, "evidence_manifest_json": canonical_json(evidence),
                    "evidence_manifest_sha256": canonical_sha256(evidence), "status": payload.status,
                    "request_sha256": request_sha256, "actor": actor, "created_at": database_datetime(now),
                })
            except Exception as exc:
                if "Duplicate" in str(exc) or "UNIQUE constraint" in str(exc):
                    raise error(409, "BRAND_ALIAS_DUPLICATE", {"entity_id": entity_id, "normalized_alias": normalized_alias}) from exc
                raise
            _append_event(conn, tenant_id=tenant_id, project_id=project_id, aggregate_type="alias", aggregate_id=alias_id, event_type="brand_alias_created", aggregate_version=1, request_sha256=request_sha256, actor=actor, trace_id=trace_id, payload=material, created_at=now)
            row = conn.execute(text("SELECT * FROM airank_brand_entity_aliases WHERE tenant_id=:tenant_id AND id=:alias_id"), {"tenant_id": tenant_id, "alias_id": alias_id}).mappings().one()
        return _alias_data(row)

    def update_alias(self, tenant_id: str, project_id: str, alias_id: str, payload: BrandAliasWriteRequest, actor: str, trace_id: str) -> BrandAliasData:
        if payload.expected_version is None:
            raise error(409, "EXPECTED_VERSION_REQUIRED", {"alias_id": alias_id})
        now = utc_now()
        with self._engine.begin() as conn:
            current = conn.execute(text("SELECT * FROM airank_brand_entity_aliases WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:alias_id"), {"tenant_id": tenant_id, "project_id": project_id, "alias_id": alias_id}).mappings().first()
            if current is None:
                raise error(404, "BRAND_ALIAS_NOT_FOUND", {"alias_id": alias_id})
            if int(current["version"]) != payload.expected_version:
                raise error(409, "STATE_VERSION_CONFLICT", {"expected_version": payload.expected_version, "actual_version": int(current["version"])})
            normalized_alias = normalize_entity_name(payload.alias_text)
            entity = self._entity_row(conn, tenant_id, project_id, str(current["entity_id"]))
            if normalized_alias == str(entity["normalized_name"]):
                raise error(409, "BRAND_ALIAS_REDUNDANT", {"entity_id": str(current["entity_id"]), "normalized_alias": normalized_alias})
            evidence = _eligible_fact_evidence(conn, tenant_id, project_id, payload.fact_revision_id, payload.usage_scope, now)
            version = payload.expected_version + 1
            material = {**payload.model_dump(mode="json", exclude={"expected_version"}), "entity_id": str(current["entity_id"]), "normalized_alias": normalized_alias, "evidence": evidence}
            request_sha256 = canonical_sha256(material)
            conn.execute(text("""
                UPDATE airank_brand_entity_aliases SET alias_text=:alias_text,
                  normalized_alias=:normalized_alias, alias_type=:alias_type,
                  language_code=:language_code, usage_scope=:usage_scope,
                  fact_revision_id=:fact_revision_id, evidence_manifest_json=:evidence_manifest_json,
                  evidence_manifest_sha256=:evidence_manifest_sha256, status=:status,
                  request_sha256=:request_sha256, version=:version, updated_by=:actor, updated_at=:updated_at
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:alias_id
            """), {
                "tenant_id": tenant_id, "project_id": project_id, "alias_id": alias_id,
                "alias_text": payload.alias_text, "normalized_alias": normalized_alias,
                "alias_type": payload.alias_type, "language_code": payload.language_code,
                "usage_scope": payload.usage_scope, "fact_revision_id": payload.fact_revision_id,
                "evidence_manifest_json": canonical_json(evidence), "evidence_manifest_sha256": canonical_sha256(evidence),
                "status": payload.status, "request_sha256": request_sha256, "version": version,
                "actor": actor, "updated_at": database_datetime(now),
            })
            _append_event(conn, tenant_id=tenant_id, project_id=project_id, aggregate_type="alias", aggregate_id=alias_id, event_type="brand_alias_updated", aggregate_version=version, request_sha256=request_sha256, actor=actor, trace_id=trace_id, payload=material, created_at=now)
            row = conn.execute(text("SELECT * FROM airank_brand_entity_aliases WHERE tenant_id=:tenant_id AND id=:alias_id"), {"tenant_id": tenant_id, "alias_id": alias_id}).mappings().one()
        return _alias_data(row)

    def _relation_entity(self, conn: Any, tenant_id: str, project_id: str, entity_id: str) -> None:
        self._entity_row(conn, tenant_id, project_id, entity_id)

    def create_relation(self, tenant_id: str, project_id: str, payload: BrandRelationWriteRequest, actor: str, trace_id: str) -> BrandRelationData:
        if payload.expected_version is not None:
            raise error(409, "EXPECTED_VERSION_NOT_ALLOWED_ON_CREATE", {"expected_version": payload.expected_version})
        now = utc_now()
        relation_id = f"brand_relation_{uuid4().hex[:16]}"
        with self._engine.begin() as conn:
            self._relation_entity(conn, tenant_id, project_id, payload.subject_entity_id)
            self._relation_entity(conn, tenant_id, project_id, payload.object_entity_id)
            evidence = _eligible_fact_evidence(conn, tenant_id, project_id, payload.fact_revision_id, payload.usage_scope, now)
            material = {**payload.model_dump(mode="json", exclude={"expected_version"}), "evidence": evidence}
            request_sha256 = canonical_sha256(material)
            try:
                conn.execute(text("""
                    INSERT INTO airank_brand_relations (
                      id, tenant_id, project_id, subject_entity_id, predicate, object_entity_id,
                      usage_scope, fact_revision_id, evidence_manifest_json,
                      evidence_manifest_sha256, status, request_sha256, version,
                      created_by, updated_by, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :subject_entity_id, :predicate, :object_entity_id,
                      :usage_scope, :fact_revision_id, :evidence_manifest_json,
                      :evidence_manifest_sha256, :status, :request_sha256, 1,
                      :actor, :actor, :created_at, :created_at
                    )
                """), {
                    "id": relation_id, "tenant_id": tenant_id, "project_id": project_id,
                    "subject_entity_id": payload.subject_entity_id, "predicate": payload.predicate,
                    "object_entity_id": payload.object_entity_id, "usage_scope": payload.usage_scope,
                    "fact_revision_id": payload.fact_revision_id, "evidence_manifest_json": canonical_json(evidence),
                    "evidence_manifest_sha256": canonical_sha256(evidence), "status": payload.status,
                    "request_sha256": request_sha256, "actor": actor, "created_at": database_datetime(now),
                })
            except Exception as exc:
                if "Duplicate" in str(exc) or "UNIQUE constraint" in str(exc):
                    raise error(409, "BRAND_RELATION_DUPLICATE", {"subject_entity_id": payload.subject_entity_id, "predicate": payload.predicate, "object_entity_id": payload.object_entity_id}) from exc
                raise
            _append_event(conn, tenant_id=tenant_id, project_id=project_id, aggregate_type="relation", aggregate_id=relation_id, event_type="brand_relation_created", aggregate_version=1, request_sha256=request_sha256, actor=actor, trace_id=trace_id, payload=material, created_at=now)
            row = conn.execute(text("SELECT * FROM airank_brand_relations WHERE tenant_id=:tenant_id AND id=:relation_id"), {"tenant_id": tenant_id, "relation_id": relation_id}).mappings().one()
        return _relation_data(row)

    def update_relation(self, tenant_id: str, project_id: str, relation_id: str, payload: BrandRelationWriteRequest, actor: str, trace_id: str) -> BrandRelationData:
        if payload.expected_version is None:
            raise error(409, "EXPECTED_VERSION_REQUIRED", {"relation_id": relation_id})
        now = utc_now()
        with self._engine.begin() as conn:
            current = conn.execute(text("SELECT * FROM airank_brand_relations WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:relation_id"), {"tenant_id": tenant_id, "project_id": project_id, "relation_id": relation_id}).mappings().first()
            if current is None:
                raise error(404, "BRAND_RELATION_NOT_FOUND", {"relation_id": relation_id})
            if int(current["version"]) != payload.expected_version:
                raise error(409, "STATE_VERSION_CONFLICT", {"expected_version": payload.expected_version, "actual_version": int(current["version"])})
            self._relation_entity(conn, tenant_id, project_id, payload.subject_entity_id)
            self._relation_entity(conn, tenant_id, project_id, payload.object_entity_id)
            evidence = _eligible_fact_evidence(conn, tenant_id, project_id, payload.fact_revision_id, payload.usage_scope, now)
            version = payload.expected_version + 1
            material = {**payload.model_dump(mode="json", exclude={"expected_version"}), "evidence": evidence}
            request_sha256 = canonical_sha256(material)
            conn.execute(text("""
                UPDATE airank_brand_relations SET subject_entity_id=:subject_entity_id,
                  predicate=:predicate, object_entity_id=:object_entity_id,
                  usage_scope=:usage_scope, fact_revision_id=:fact_revision_id,
                  evidence_manifest_json=:evidence_manifest_json,
                  evidence_manifest_sha256=:evidence_manifest_sha256, status=:status,
                  request_sha256=:request_sha256, version=:version, updated_by=:actor, updated_at=:updated_at
                WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:relation_id
            """), {
                "tenant_id": tenant_id, "project_id": project_id, "relation_id": relation_id,
                "subject_entity_id": payload.subject_entity_id, "predicate": payload.predicate,
                "object_entity_id": payload.object_entity_id, "usage_scope": payload.usage_scope,
                "fact_revision_id": payload.fact_revision_id, "evidence_manifest_json": canonical_json(evidence),
                "evidence_manifest_sha256": canonical_sha256(evidence), "status": payload.status,
                "request_sha256": request_sha256, "version": version, "actor": actor, "updated_at": database_datetime(now),
            })
            _append_event(conn, tenant_id=tenant_id, project_id=project_id, aggregate_type="relation", aggregate_id=relation_id, event_type="brand_relation_updated", aggregate_version=version, request_sha256=request_sha256, actor=actor, trace_id=trace_id, payload=material, created_at=now)
            row = conn.execute(text("SELECT * FROM airank_brand_relations WHERE tenant_id=:tenant_id AND id=:relation_id"), {"tenant_id": tenant_id, "relation_id": relation_id}).mappings().one()
        return _relation_data(row)

    def compile_snapshot(self, tenant_id: str, project_id: str, actor: str) -> BrandGraphSnapshotData:
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            return compile_or_reuse_brand_graph_snapshot(conn, tenant_id, project_id, created_by=actor)

    def get_snapshot(self, tenant_id: str, snapshot_id: str) -> BrandGraphSnapshotData:
        with self._engine.begin() as conn:
            row = conn.execute(text("SELECT project_id FROM airank_brand_graph_snapshots WHERE tenant_id=:tenant_id AND id=:snapshot_id"), {"tenant_id": tenant_id, "snapshot_id": snapshot_id}).mappings().first()
            if row is None:
                raise error(404, "BRAND_GRAPH_SNAPSHOT_NOT_FOUND", {"snapshot_id": snapshot_id})
            return load_brand_graph_snapshot(conn, tenant_id, str(row["project_id"]), snapshot_id)

    def portfolio(self, tenant_id: str, project_id: str) -> BrandGraphPortfolioData:
        with self._engine.begin() as conn:
            self._ensure_project(conn, tenant_id, project_id)
            entities = [_entity_data(row) for row in conn.execute(text("SELECT * FROM airank_brand_entities WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY entity_role, entity_kind, normalized_name, id"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()]
            aliases = [_alias_data(row) for row in conn.execute(text("SELECT * FROM airank_brand_entity_aliases WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY normalized_alias, id"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()]
            relations = [_relation_data(row) for row in conn.execute(text("SELECT * FROM airank_brand_relations WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY subject_entity_id, predicate, object_entity_id, id"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().all()]
            latest_row = conn.execute(text("SELECT * FROM airank_brand_graph_snapshots WHERE tenant_id=:tenant_id AND project_id=:project_id ORDER BY created_at DESC, id DESC LIMIT 1"), {"tenant_id": tenant_id, "project_id": project_id}).mappings().first()
        latest = _snapshot_data(latest_row) if latest_row is not None else None
        limitations = latest.known_limitations if latest else ["brand_graph_snapshot_not_compiled"]
        return BrandGraphPortfolioData(
            project_id=project_id,
            entities=entities,
            aliases=aliases,
            relations=relations,
            latest_snapshot=latest,
            measurement_ready=latest is not None and latest.status in {"governed", "partial", "legacy_unverified"},
            public_export_ready=latest is not None and latest.status in {"governed", "partial"} and bool(latest.public_jsonld),
            known_limitations=limitations,
        )


def build_brand_graph_repository() -> BrandGraphRepository:
    database_url = os.getenv("AIRANK_DATABASE_URL")
    return MySQLBrandGraphRepository(database_url) if database_url else InMemoryBrandGraphRepository()


BRAND_GRAPH_REPOSITORY: BrandGraphRepository = build_brand_graph_repository()


def _write_context(permission_header: Optional[str], authenticated_actor: Optional[str], trace_id: Optional[str]) -> tuple[str, str]:
    require_brand_graph_admin(permission_header)
    return trusted_actor(authenticated_actor), trace_id or f"trc_{uuid4().hex[:16]}"


@router.get("/projects/{project_id}/brand-graph", response_model=BrandGraphPortfolioResponse)
def get_brand_graph(project_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id")) -> BrandGraphPortfolioResponse:
    return BrandGraphPortfolioResponse(data=BRAND_GRAPH_REPOSITORY.portfolio(tenant_id, project_id), meta=response_meta(trace_id))


@router.post("/projects/{project_id}/brand-entities", response_model=BrandEntityResponse, status_code=201)
def create_brand_entity(project_id: str, payload: BrandEntityWriteRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandEntityResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandEntityResponse(data=BRAND_GRAPH_REPOSITORY.create_entity(tenant_id, project_id, payload, actor, trusted_trace), meta=response_meta(trusted_trace))


@router.put("/projects/{project_id}/brand-entities/{entity_id}", response_model=BrandEntityResponse)
def update_brand_entity(project_id: str, entity_id: str, payload: BrandEntityWriteRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandEntityResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandEntityResponse(data=BRAND_GRAPH_REPOSITORY.update_entity(tenant_id, project_id, entity_id, payload, actor, trusted_trace), meta=response_meta(trusted_trace))


@router.post("/projects/{project_id}/brand-entities/{entity_id}/aliases", response_model=BrandAliasResponse, status_code=201)
def create_brand_alias(project_id: str, entity_id: str, payload: BrandAliasWriteRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandAliasResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandAliasResponse(data=BRAND_GRAPH_REPOSITORY.create_alias(tenant_id, project_id, entity_id, payload, actor, trusted_trace), meta=response_meta(trusted_trace))


@router.put("/projects/{project_id}/brand-aliases/{alias_id}", response_model=BrandAliasResponse)
def update_brand_alias(project_id: str, alias_id: str, payload: BrandAliasWriteRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandAliasResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandAliasResponse(data=BRAND_GRAPH_REPOSITORY.update_alias(tenant_id, project_id, alias_id, payload, actor, trusted_trace), meta=response_meta(trusted_trace))


@router.post("/projects/{project_id}/brand-relations", response_model=BrandRelationResponse, status_code=201)
def create_brand_relation(project_id: str, payload: BrandRelationWriteRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandRelationResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandRelationResponse(data=BRAND_GRAPH_REPOSITORY.create_relation(tenant_id, project_id, payload, actor, trusted_trace), meta=response_meta(trusted_trace))


@router.put("/projects/{project_id}/brand-relations/{relation_id}", response_model=BrandRelationResponse)
def update_brand_relation(project_id: str, relation_id: str, payload: BrandRelationWriteRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandRelationResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandRelationResponse(data=BRAND_GRAPH_REPOSITORY.update_relation(tenant_id, project_id, relation_id, payload, actor, trusted_trace), meta=response_meta(trusted_trace))


@router.post("/projects/{project_id}/brand-graph/snapshots", response_model=BrandGraphSnapshotResponse, status_code=201)
def compile_brand_graph(project_id: str, payload: BrandGraphCompileRequest, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id"), authenticated_actor: Optional[str] = Header(default=None, alias="X-AIRank-User-Id"), permission_header: Optional[str] = Header(default=None, alias="X-AIRank-Permissions")) -> BrandGraphSnapshotResponse:
    actor, trusted_trace = _write_context(permission_header, authenticated_actor, trace_id)
    return BrandGraphSnapshotResponse(data=BRAND_GRAPH_REPOSITORY.compile_snapshot(tenant_id, project_id, actor), meta=response_meta(trusted_trace))


@router.get("/brand-graph-snapshots/{snapshot_id}", response_model=BrandGraphSnapshotResponse)
def get_brand_graph_snapshot(snapshot_id: str, tenant_id: str = Header(default="tenant_demo", alias="tenant-id"), trace_id: Optional[str] = Header(default=None, alias="X-AIRank-Trace-Id")) -> BrandGraphSnapshotResponse:
    return BrandGraphSnapshotResponse(data=BRAND_GRAPH_REPOSITORY.get_snapshot(tenant_id, snapshot_id), meta=response_meta(trace_id))
