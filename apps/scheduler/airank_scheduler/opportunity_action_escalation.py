from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import create_engine, text


ACTION_SLA_ESCALATION_EVENT = "opportunity_action.sla_overdue.v1"
ACTION_SLA_ESCALATION_SCHEMA = "airank.opportunity-action-sla-escalation.v1"
MAX_ESCALATION_SCAN_ACTIONS = 10_000
ACTIVE_STATUSES = ("open", "in_progress", "evidence_blocked")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("opportunity action escalation timestamp is missing")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def database_datetime(value: datetime) -> datetime:
    return utc_datetime(value).replace(tzinfo=None)


def stable_event_id(tenant_id: str, action_id: str, due_at: datetime) -> str:
    basis = "\x1f".join(
        [tenant_id, action_id, utc_datetime(due_at).isoformat(timespec="milliseconds")]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"opportunity_sla_{digest[:40]}"


@dataclass(frozen=True)
class OpportunityActionEscalationPreview:
    overdue_action_count: int
    pending_event_count: int
    dispatchable_count: int
    next_due_action_id: str | None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class OpportunityActionEscalationRecord:
    event_id: str
    tenant_id: str
    project_id: str
    action_id: str
    opportunity_id: str
    source_kind: str
    due_at: datetime
    escalated_at: datetime
    overdue_seconds: int
    assignment_state: str
    routing_state: str
    routing_team_id: str | None
    routing_route_version: int | None
    eligible_recipient_count: int
    external_sync_state: str
    outbox_status: str

    def to_record(self) -> dict[str, object]:
        return asdict(self)


class MySQLOpportunityActionEscalationScheduler:
    """Persists overdue action SLA events without claiming external delivery."""

    def __init__(
        self,
        database_url: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        scheduler_id: str = "airank-opportunity-action-escalation-scheduler",
    ) -> None:
        if project_id and not tenant_id:
            raise ValueError("project scope requires tenant scope")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.scheduler_id = scheduler_id

    def preview(self, now: datetime | None = None) -> OpportunityActionEscalationPreview:
        checked_at = utc_datetime(now or utc_now())
        candidates = self._overdue_candidates(checked_at)
        existing = self._existing_events(item["event_id"] for item in candidates)
        dispatchable = [item for item in candidates if item["event_id"] not in existing]
        return OpportunityActionEscalationPreview(
            overdue_action_count=len(candidates),
            pending_event_count=sum(1 for value in existing.values() if value == "pending"),
            dispatchable_count=len(dispatchable),
            next_due_action_id=(
                str(dispatchable[0]["action_id"]) if dispatchable else None
            ),
        )

    def dispatch_overdue(
        self, *, now: datetime | None = None, limit: int = 10
    ) -> list[OpportunityActionEscalationRecord]:
        if limit < 1 or limit > 500:
            raise ValueError("opportunity action escalation limit must be between 1 and 500")
        escalated_at = utc_datetime(now or utc_now())
        records: list[OpportunityActionEscalationRecord] = []
        for candidate in self._overdue_candidates(escalated_at):
            if len(records) >= limit:
                break
            with self.engine.begin() as conn:
                fresh = self._load_candidate_for_update(conn, candidate, escalated_at)
                if fresh is None:
                    continue
                candidate = fresh
                route = self._route_snapshot(conn, candidate)
                payload = {
                    "schema_version": ACTION_SLA_ESCALATION_SCHEMA,
                    "action_id": candidate["action_id"],
                    "opportunity_id": candidate["opportunity_id"],
                    "source_kind": candidate["source_kind"],
                    "action_status": candidate["status"],
                    "due_at": candidate["due_at"].isoformat(),
                    "escalated_at": escalated_at.isoformat(),
                    "overdue_seconds": candidate["overdue_seconds"],
                    "assignment_state": candidate["assignment_state"],
                    "routing_state": candidate["routing_state"],
                    "routing_team_id": candidate["routing_team_id"],
                    "routing_route_version": candidate["routing_route_version"],
                    "eligible_recipient_count": route["eligible_recipient_count"],
                    "external_sync_state": route["external_sync_state"],
                    "effect_claim_allowed": False,
                    "delivery_claim": "outbox_pending_not_delivered",
                }
                insert_prefix = "INSERT IGNORE" if self.engine.dialect.name == "mysql" else "INSERT OR IGNORE"
                result = conn.execute(
                    text(
                        f"""
                        {insert_prefix} INTO airank_outbox_events (
                          id, tenant_id, project_id, event_type, aggregate_type,
                          aggregate_id, trace_id, status, available_at,
                          attempt_count, payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :event_type,
                          'opportunity_action', :action_id, :trace_id, 'pending',
                          :available_at, 0, :payload_json, :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": candidate["event_id"],
                        "tenant_id": candidate["tenant_id"],
                        "project_id": candidate["project_id"],
                        "event_type": ACTION_SLA_ESCALATION_EVENT,
                        "action_id": candidate["action_id"],
                        "trace_id": f"opportunity-sla:{self.scheduler_id}",
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
                OpportunityActionEscalationRecord(
                    event_id=str(candidate["event_id"]),
                    tenant_id=str(candidate["tenant_id"]),
                    project_id=str(candidate["project_id"]),
                    action_id=str(candidate["action_id"]),
                    opportunity_id=str(candidate["opportunity_id"]),
                    source_kind=str(candidate["source_kind"]),
                    due_at=candidate["due_at"],
                    escalated_at=escalated_at,
                    overdue_seconds=int(candidate["overdue_seconds"]),
                    assignment_state=str(candidate["assignment_state"]),
                    routing_state=str(candidate["routing_state"]),
                    routing_team_id=(
                        str(candidate["routing_team_id"])
                        if candidate["routing_team_id"]
                        else None
                    ),
                    routing_route_version=(
                        int(candidate["routing_route_version"])
                        if candidate["routing_route_version"] is not None
                        else None
                    ),
                    eligible_recipient_count=int(route["eligible_recipient_count"]),
                    external_sync_state=str(route["external_sync_state"]),
                    outbox_status="pending",
                )
            )
        return records

    def _overdue_candidates(self, checked_at: datetime) -> list[dict[str, Any]]:
        scope_sql, params = self._scope_sql("action")
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT action.*
                    FROM airank_opportunity_actions action
                    WHERE action.status IN ('open','in_progress','evidence_blocked')
                      AND action.due_at<=:checked_at {scope_sql}
                    ORDER BY action.due_at, action.id
                    LIMIT {MAX_ESCALATION_SCAN_ACTIONS + 1}
                    """
                ),
                {**params, "checked_at": database_datetime(checked_at)},
            ).mappings().all()
        if len(rows) > MAX_ESCALATION_SCAN_ACTIONS:
            raise ValueError("OPPORTUNITY_ACTION_ESCALATION_SCOPE_TOO_LARGE")
        return [self._candidate(row, checked_at) for row in rows]

    def _load_candidate_for_update(
        self,
        conn: Any,
        expected: Mapping[str, Any],
        checked_at: datetime,
    ) -> dict[str, Any] | None:
        suffix = " FOR UPDATE" if self.engine.dialect.name == "mysql" else ""
        row = conn.execute(
            text(
                "SELECT * FROM airank_opportunity_actions "
                "WHERE tenant_id=:tenant_id AND project_id=:project_id AND id=:action_id "
                "AND status IN ('open','in_progress','evidence_blocked') "
                "AND due_at<=:checked_at" + suffix
            ),
            {
                "tenant_id": expected["tenant_id"],
                "project_id": expected["project_id"],
                "action_id": expected["action_id"],
                "checked_at": database_datetime(checked_at),
            },
        ).mappings().first()
        if row is None:
            return None
        candidate = self._candidate(row, checked_at)
        return candidate if candidate["event_id"] == expected["event_id"] else None

    @staticmethod
    def _candidate(row: Mapping[str, Any], checked_at: datetime) -> dict[str, Any]:
        due_at = utc_datetime(row["due_at"])
        action_id = str(row["id"])
        return {
            "event_id": stable_event_id(str(row["tenant_id"]), action_id, due_at),
            "tenant_id": str(row["tenant_id"]),
            "project_id": str(row["project_id"]),
            "action_id": action_id,
            "opportunity_id": str(row["opportunity_id"]),
            "source_kind": str(row["source_kind"]),
            "status": str(row["status"]),
            "due_at": due_at,
            "overdue_seconds": max(0, int((checked_at - due_at).total_seconds())),
            "assignment_state": "assigned" if row["assigned_to"] else "unassigned",
            "routing_state": str(row["routing_state"]),
            "routing_team_id": row["routing_team_id"],
            "routing_route_version": row["routing_route_version"],
        }

    @staticmethod
    def _route_snapshot(conn: Any, candidate: Mapping[str, Any]) -> dict[str, object]:
        team_id = candidate.get("routing_team_id")
        if not team_id:
            return {
                "eligible_recipient_count": 0,
                "external_sync_state": "not_configured",
            }
        row = conn.execute(
            text(
                """
                SELECT team.external_sync_state,
                       SUM(CASE WHEN member.status='active'
                                      AND member.receives_escalations=1
                                THEN 1 ELSE 0 END) AS recipient_count
                FROM airank_opportunity_action_teams team
                LEFT JOIN airank_opportunity_action_team_members member
                  ON member.tenant_id=team.tenant_id AND member.team_id=team.id
                WHERE team.tenant_id=:tenant_id AND team.project_id=:project_id
                  AND team.id=:team_id
                GROUP BY team.id, team.external_sync_state
                """
            ),
            {
                "tenant_id": candidate["tenant_id"],
                "project_id": candidate["project_id"],
                "team_id": team_id,
            },
        ).mappings().first()
        return {
            "eligible_recipient_count": int(row["recipient_count"] or 0) if row else 0,
            "external_sync_state": str(row["external_sync_state"]) if row else "stale",
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
