from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import create_engine, text

from apps.api.evidence_review_routes import review_sla_seconds


REVIEW_SLA_ESCALATION_EVENT = "evidence_review.sla_overdue.v1"
REVIEW_SLA_ESCALATION_SCHEMA = "airank.evidence-review-sla-escalation.v1"
MAX_ESCALATION_SCAN_CASES = 10_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("review escalation timestamp is missing")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    normalized = utc_datetime(value)
    return normalized.replace(tzinfo=None)


def stable_event_id(tenant_id: str, case_id: str, role: str, due_at: datetime) -> str:
    basis = "\x1f".join(
        [tenant_id, case_id, role, utc_datetime(due_at).isoformat(timespec="milliseconds")]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"review_sla_{digest[:40]}"


def json_object(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


@dataclass(frozen=True)
class ReviewEscalationQueuePreview:
    overdue_case_count: int
    pending_event_count: int
    dispatchable_count: int
    next_due_case_id: str | None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewEscalationDispatchRecord:
    event_id: str
    tenant_id: str
    project_id: str
    case_id: str
    reviewer_role: str
    due_at: datetime
    escalated_at: datetime
    overdue_seconds: int
    assignment_state: str
    outbox_status: str

    def to_record(self) -> dict[str, object]:
        return asdict(self)


class MySQLReviewEscalationScheduler:
    """Persists overdue reviewer-SLA events without claiming external delivery."""

    def __init__(
        self,
        database_url: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        scheduler_id: str = "airank-review-escalation-scheduler",
    ) -> None:
        if project_id and not tenant_id:
            raise ValueError("project scope requires tenant scope")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.scheduler_id = scheduler_id

    def preview(self, now: datetime | None = None) -> ReviewEscalationQueuePreview:
        checked_at = utc_datetime(now or utc_now())
        candidates = self._overdue_candidates(checked_at)
        existing = self._existing_events(item["event_id"] for item in candidates)
        pending_count = sum(1 for status in existing.values() if status == "pending")
        dispatchable = [item for item in candidates if item["event_id"] not in existing]
        return ReviewEscalationQueuePreview(
            overdue_case_count=len(candidates),
            pending_event_count=pending_count,
            dispatchable_count=len(dispatchable),
            next_due_case_id=(str(dispatchable[0]["case_id"]) if dispatchable else None),
        )

    def dispatch_overdue(
        self, *, now: datetime | None = None, limit: int = 10
    ) -> list[ReviewEscalationDispatchRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("review escalation limit must be between 1 and 500")
        escalated_at = utc_datetime(now or utc_now())
        candidates = self._overdue_candidates(escalated_at)
        records: list[ReviewEscalationDispatchRecord] = []
        for candidate in candidates:
            if len(records) >= limit:
                break
            with self.engine.begin() as conn:
                fresh_candidate = self._load_candidate_for_update(
                    conn, candidate, escalated_at
                )
                if fresh_candidate is None:
                    continue
                candidate = fresh_candidate
                payload = {
                    "schema_version": REVIEW_SLA_ESCALATION_SCHEMA,
                    "case_id": candidate["case_id"],
                    "reviewer_role": candidate["reviewer_role"],
                    "due_at": candidate["due_at"].isoformat(),
                    "escalated_at": escalated_at.isoformat(),
                    "overdue_seconds": candidate["overdue_seconds"],
                    "assignment_state": candidate["assignment_state"],
                    "delivery_claim": "outbox_pending_not_delivered",
                }
                if self.engine.dialect.name == "mysql":
                    statement = """
                        INSERT IGNORE INTO airank_outbox_events (
                          id, tenant_id, project_id, event_type, aggregate_type,
                          aggregate_id, trace_id, status, available_at,
                          attempt_count, payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :event_type,
                          'evidence_review_case', :case_id, :trace_id, 'pending',
                          :available_at, 0, :payload_json, :created_at, :updated_at
                        )
                    """
                else:
                    statement = """
                        INSERT OR IGNORE INTO airank_outbox_events (
                          id, tenant_id, project_id, event_type, aggregate_type,
                          aggregate_id, trace_id, status, available_at,
                          attempt_count, payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :event_type,
                          'evidence_review_case', :case_id, :trace_id, 'pending',
                          :available_at, 0, :payload_json, :created_at, :updated_at
                        )
                    """
                result = conn.execute(
                    text(statement),
                    {
                        "id": candidate["event_id"],
                        "tenant_id": candidate["tenant_id"],
                        "project_id": candidate["project_id"],
                        "event_type": REVIEW_SLA_ESCALATION_EVENT,
                        "case_id": candidate["case_id"],
                        "trace_id": f"review-sla:{self.scheduler_id}",
                        "available_at": database_datetime(escalated_at),
                        "payload_json": json.dumps(
                            payload, ensure_ascii=False, sort_keys=True
                        ),
                        "created_at": database_datetime(escalated_at),
                        "updated_at": database_datetime(escalated_at),
                    },
                )
                inserted = int(result.rowcount or 0) == 1
            if not inserted:
                continue
            records.append(
                ReviewEscalationDispatchRecord(
                    event_id=str(candidate["event_id"]),
                    tenant_id=str(candidate["tenant_id"]),
                    project_id=str(candidate["project_id"]),
                    case_id=str(candidate["case_id"]),
                    reviewer_role=str(candidate["reviewer_role"]),
                    due_at=candidate["due_at"],
                    escalated_at=escalated_at,
                    overdue_seconds=int(candidate["overdue_seconds"]),
                    assignment_state=str(candidate["assignment_state"]),
                    outbox_status="pending",
                )
            )
        return records

    def _overdue_candidates(self, checked_at: datetime) -> list[dict[str, Any]]:
        scope_sql, params = self._scope_sql("c")
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT c.id AS case_id, c.tenant_id, c.project_id, c.status,
                           c.created_at, c.updated_at,
                           a.id AS assignment_id, a.due_at AS assignment_due_at,
                           a.lease_expires_at
                    FROM airank_evidence_review_cases c
                    LEFT JOIN airank_evidence_review_assignments a
                      ON a.tenant_id=c.tenant_id AND a.case_id=c.id
                     AND a.status='active'
                     AND a.reviewer_role=(
                       CASE WHEN c.status='awaiting_secondary'
                            THEN 'secondary' ELSE 'adjudicator' END
                     )
                    WHERE c.status IN ('awaiting_secondary','disputed') {scope_sql}
                    ORDER BY c.created_at, c.id
                    LIMIT {MAX_ESCALATION_SCAN_CASES + 1}
                    """
                ),
                params,
            ).mappings().all()
        if len(rows) > MAX_ESCALATION_SCAN_CASES:
            raise ValueError("REVIEW_ESCALATION_SCOPE_TOO_LARGE")
        candidates: list[dict[str, Any]] = []
        for row in rows:
            candidate = self._candidate_from_row(row, checked_at)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda item: (item["due_at"], item["case_id"]))
        return candidates

    def _load_candidate_for_update(
        self,
        conn: Any,
        expected: Mapping[str, Any],
        checked_at: datetime,
    ) -> dict[str, Any] | None:
        lock_suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        row = conn.execute(
            text(
                f"""
                SELECT c.id AS case_id, c.tenant_id, c.project_id, c.status,
                       c.created_at, c.updated_at,
                       a.id AS assignment_id, a.due_at AS assignment_due_at,
                       a.lease_expires_at
                FROM airank_evidence_review_cases c
                LEFT JOIN airank_evidence_review_assignments a
                  ON a.tenant_id=c.tenant_id AND a.case_id=c.id
                 AND a.status='active'
                 AND a.reviewer_role=(
                   CASE WHEN c.status='awaiting_secondary'
                        THEN 'secondary' ELSE 'adjudicator' END
                 )
                WHERE c.tenant_id=:tenant_id AND c.id=:case_id
                  AND c.status IN ('awaiting_secondary','disputed')
                {lock_suffix}
                """
            ),
            {
                "tenant_id": expected["tenant_id"],
                "case_id": expected["case_id"],
            },
        ).mappings().first()
        if row is None:
            return None
        candidate = self._candidate_from_row(row, checked_at)
        if candidate is None or candidate["event_id"] != expected["event_id"]:
            return None
        return candidate

    @staticmethod
    def _candidate_from_row(
        row: Mapping[str, Any], checked_at: datetime
    ) -> dict[str, Any] | None:
        status = str(row["status"])
        if status not in {"awaiting_secondary", "disputed"}:
            return None
        role = "secondary" if status == "awaiting_secondary" else "adjudicator"
        action_available_at = utc_datetime(
            row["created_at"] if role == "secondary" else row["updated_at"]
        )
        due_at = (
            utc_datetime(row["assignment_due_at"])
            if row["assignment_due_at"] is not None
            else action_available_at + timedelta(seconds=review_sla_seconds(role))
        )
        if due_at > checked_at:
            return None
        assignment_state = "unassigned"
        if row["assignment_id"] is not None:
            assignment_state = (
                "expired"
                if utc_datetime(row["lease_expires_at"]) <= checked_at
                else "assigned"
            )
        return {
            "event_id": stable_event_id(
                str(row["tenant_id"]), str(row["case_id"]), role, due_at
            ),
            "tenant_id": str(row["tenant_id"]),
            "project_id": str(row["project_id"]),
            "case_id": str(row["case_id"]),
            "reviewer_role": role,
            "due_at": due_at,
            "overdue_seconds": max(0, int((checked_at - due_at).total_seconds())),
            "assignment_state": assignment_state,
            "assignment_id": (
                str(row["assignment_id"])
                if row["assignment_id"] is not None
                else None
            ),
        }

    def _existing_events(self, event_ids: Any) -> dict[str, str]:
        ids = tuple(str(value) for value in event_ids)
        if not ids:
            return {}
        placeholders = ",".join(f":event_{index}" for index in range(len(ids)))
        params = {f"event_{index}": event_id for index, event_id in enumerate(ids)}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"SELECT id, status FROM airank_outbox_events "
                    f"WHERE id IN ({placeholders})"
                ),
                params,
            ).all()
        return {str(row[0]): str(row[1]) for row in rows}

    def _scope_sql(self, alias: str) -> tuple[str, dict[str, object]]:
        clauses: list[str] = []
        params: dict[str, object] = {}
        if self.tenant_id:
            clauses.append(f"{alias}.tenant_id=:scope_tenant_id")
            params["scope_tenant_id"] = self.tenant_id
        if self.project_id:
            clauses.append(f"{alias}.project_id=:scope_project_id")
            params["scope_project_id"] = self.project_id
        return (" AND " + " AND ".join(clauses) if clauses else ""), params
