from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from sqlalchemy import create_engine, text


@dataclass(frozen=True)
class RetestQueuePreview:
    due_window_count: int
    ready_to_finalize_count: int
    next_due_window_id: str | None
    next_finalize_window_id: str | None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RetestDispatchRecord:
    window_id: str
    action: str
    compare_run_id: str | None
    task_count: int
    job_count: int
    error_code: str | None = None

    def to_record(self) -> dict[str, object]:
        return asdict(self)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _json_storage(value: object, fallback: object) -> str:
    if value is None:
        value = fallback
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = fallback
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


class MySQLRetestScheduler:
    """Schedules comparable retest ScanRuns from immutable baseline task contracts."""

    def __init__(
        self,
        database_url: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
        window_id: str | None = None,
        scheduler_id: str = "airank-retest-scheduler",
    ) -> None:
        if project_id and not tenant_id:
            raise ValueError("project scope requires tenant scope")
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.window_id = window_id
        self.scheduler_id = scheduler_id

    def preview(self, now: datetime | None = None) -> RetestQueuePreview:
        checked_at = now or utc_now()
        scope_sql, params = self._scope_sql("w")
        params["now"] = checked_at
        with self.engine.begin() as conn:
            due_rows = conn.execute(
                text(
                    f"""
                    SELECT w.id
                    FROM airank_retest_observation_windows w
                    WHERE w.status='scheduled' AND w.due_at<=:now {scope_sql}
                    ORDER BY w.due_at, w.id
                    """
                ),
                params,
            ).all()
            ready_rows = conn.execute(
                text(
                    f"""
                    SELECT w.id
                    FROM airank_retest_observation_windows w
                    JOIN airank_scan_runs r
                      ON r.tenant_id=w.tenant_id AND r.id=w.compare_run_id
                    WHERE w.status='sampling'
                      AND r.status IN ('completed','failed') {scope_sql}
                    ORDER BY w.due_at, w.id
                    """
                ),
                params,
            ).all()
        return RetestQueuePreview(
            due_window_count=len(due_rows),
            ready_to_finalize_count=len(ready_rows),
            next_due_window_id=str(due_rows[0][0]) if due_rows else None,
            next_finalize_window_id=str(ready_rows[0][0]) if ready_rows else None,
        )

    def dispatch_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 10,
    ) -> list[RetestDispatchRecord]:
        if limit < 1:
            raise ValueError("dispatch limit must be positive")
        dispatched_at = now or utc_now()
        records: list[RetestDispatchRecord] = []
        for _ in range(limit):
            record = self._dispatch_one(dispatched_at)
            if record is None:
                break
            records.append(record)
        return records

    def ready_to_finalize(self, *, limit: int = 10) -> list[dict[str, str]]:
        if limit < 1:
            raise ValueError("finalize limit must be positive")
        scope_sql, params = self._scope_sql("w")
        params["limit"] = limit
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT w.id AS window_id, w.tenant_id, w.project_id,
                           w.compare_run_id, r.status AS run_status
                    FROM airank_retest_observation_windows w
                    JOIN airank_scan_runs r
                      ON r.tenant_id=w.tenant_id AND r.id=w.compare_run_id
                    WHERE w.status='sampling'
                      AND r.status IN ('completed','failed') {scope_sql}
                    ORDER BY w.due_at, w.id
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [
            {
                "window_id": str(row["window_id"]),
                "tenant_id": str(row["tenant_id"]),
                "project_id": str(row["project_id"]),
                "compare_run_id": str(row["compare_run_id"]),
                "run_status": str(row["run_status"]),
            }
            for row in rows
        ]

    def _dispatch_one(self, dispatched_at: datetime) -> RetestDispatchRecord | None:
        scope_sql, params = self._scope_sql("w")
        params["now"] = dispatched_at
        lock_sql = " FOR UPDATE SKIP LOCKED" if self.engine.dialect.name == "mysql" else ""
        with self.engine.begin() as conn:
            window = conn.execute(
                text(
                    f"""
                    SELECT w.*, b.status AS baseline_status,
                           b.provider_scope_json, b.question_scope_json,
                           b.model_route_snapshot
                    FROM airank_retest_observation_windows w
                    LEFT JOIN airank_scan_runs b
                      ON b.tenant_id=w.tenant_id AND b.id=w.baseline_run_id
                    WHERE w.status='scheduled' AND w.due_at<=:now {scope_sql}
                    ORDER BY w.due_at, w.id
                    LIMIT 1{lock_sql}
                    """
                ),
                params,
            ).mappings().first()
            if window is None:
                return None
            window_id = str(window["id"])
            tenant_id = str(window["tenant_id"])
            project_id = str(window["project_id"])
            baseline_run_id = str(window["baseline_run_id"] or "")
            if not baseline_run_id or str(window["baseline_status"] or "") != "completed":
                return self._block_window(
                    conn,
                    window_id=window_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    now=dispatched_at,
                    error_code="RETEST_BASELINE_NOT_READY",
                )
            if str(window["window_label"]) == "T0":
                result = {
                    "contract_version": "airank.retest-baseline-anchor.v1",
                    "baseline_run_id": baseline_run_id,
                    "observation": "T0 baseline recorded at publication evidence time",
                }
                conn.execute(
                    text(
                        """
                        UPDATE airank_retest_observation_windows
                        SET status='completed', compare_run_id=:baseline_run_id,
                            result_json=:result_json, completed_at=:now, updated_at=:now
                        WHERE tenant_id=:tenant_id AND id=:window_id AND status='scheduled'
                        """
                    ),
                    {
                        "baseline_run_id": baseline_run_id,
                        "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
                        "now": dispatched_at,
                        "tenant_id": tenant_id,
                        "window_id": window_id,
                    },
                )
                self._audit(
                    conn,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    window_id=window_id,
                    event_type="retest.baseline_recorded",
                    payload=result,
                    now=dispatched_at,
                )
                return RetestDispatchRecord(window_id, "baseline_recorded", baseline_run_id, 0, 0)

            baseline_tasks = conn.execute(
                text(
                    """
                    SELECT id, question_id, provider, cohort_type, prompt_version_id,
                           sample_index, collector_surface, evidence_level, request_json
                    FROM airank_scan_tasks
                    WHERE tenant_id=:tenant_id AND project_id=:project_id
                      AND run_id=:baseline_run_id
                    ORDER BY question_id, provider, collector_surface, sample_index, id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "baseline_run_id": baseline_run_id,
                },
            ).mappings().all()
            if not baseline_tasks:
                return self._block_window(
                    conn,
                    window_id=window_id,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    now=dispatched_at,
                    error_code="RETEST_BASELINE_TASKS_MISSING",
                )
            frozen_tasks: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
            for task in baseline_tasks:
                request = _json_object(task["request_json"])
                if not str(request.get("question_text") or "").strip():
                    return self._block_window(
                        conn,
                        window_id=window_id,
                        tenant_id=tenant_id,
                        project_id=project_id,
                        now=dispatched_at,
                        error_code="RETEST_FROZEN_PROMPT_MISSING",
                    )
                frozen_tasks.append((task, request))

            compare_run_id = _stable_id("scan_run_retest", tenant_id, window_id)
            conn.execute(
                text(
                    """
                    INSERT INTO airank_scan_runs (
                      id, tenant_id, project_id, name, run_type, status,
                      provider_scope_json, question_scope_json, model_route_snapshot,
                      metrics_json, created_by, created_at, updated_at
                    ) VALUES (
                      :id, :tenant_id, :project_id, :name, 'retest', 'queued',
                      :provider_scope_json, :question_scope_json, :model_route_snapshot,
                      :metrics_json, :created_by, :created_at, :created_at
                    )
                    """
                ),
                {
                    "id": compare_run_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "name": f"{window['window_label']} scheduled retest",
                    "provider_scope_json": _json_storage(window["provider_scope_json"], []),
                    "question_scope_json": _json_storage(window["question_scope_json"], {}),
                    "model_route_snapshot": _json_storage(window["model_route_snapshot"], {}),
                    "metrics_json": json.dumps(
                        {
                            "contract_version": "airank.retest-dispatch.v1",
                            "baseline_run_id": baseline_run_id,
                            "observation_window_id": window_id,
                            "window_label": str(window["window_label"]),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "created_by": self.scheduler_id,
                    "created_at": dispatched_at,
                },
            )
            for baseline_task, request in frozen_tasks:
                baseline_task_id = str(baseline_task["id"])
                task_id = _stable_id("scan_task_retest", window_id, baseline_task_id)
                job_id = _stable_id("job_retest", window_id, baseline_task_id)
                session_id = _stable_id("session_retest", window_id, baseline_task_id, length=32)
                request.update(
                    {
                        "run_id": compare_run_id,
                        "scan_task_id": task_id,
                        "project_id": project_id,
                        "session_id": session_id,
                        "baseline_run_id": baseline_run_id,
                        "baseline_task_id": baseline_task_id,
                        "retest_window_id": window_id,
                    }
                )
                request_json = json.dumps(request, ensure_ascii=False, sort_keys=True)
                task_params = {
                    "id": task_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": compare_run_id,
                    "question_id": str(baseline_task["question_id"]),
                    "provider": str(baseline_task["provider"]),
                    "cohort_type": str(baseline_task["cohort_type"]),
                    "prompt_version_id": str(baseline_task["prompt_version_id"]),
                    "sample_index": int(baseline_task["sample_index"]),
                    "session_id": session_id,
                    "collector_surface": str(baseline_task["collector_surface"]),
                    "evidence_level": str(baseline_task["evidence_level"]),
                    "request_json": request_json,
                    "now": dispatched_at,
                }
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_scan_tasks (
                          id, tenant_id, project_id, run_id, question_id, provider,
                          cohort_type, prompt_version_id, sample_index, session_id,
                          collector_surface, evidence_level, status, attempt_count,
                          scheduled_at, request_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, :run_id, :question_id, :provider,
                          :cohort_type, :prompt_version_id, :sample_index, :session_id,
                          :collector_surface, :evidence_level, 'queued', 0,
                          :now, :request_json, :now, :now
                        )
                        """
                    ),
                    task_params,
                )
                conn.execute(
                    text(
                        """
                        INSERT INTO airank_async_jobs (
                          id, tenant_id, project_id, job_type, status, priority,
                          scheduled_at, payload_json, created_at, updated_at
                        ) VALUES (
                          :id, :tenant_id, :project_id, 'scan.provider', 'queued', 100,
                          :now, :payload_json, :now, :now
                        )
                        """
                    ),
                    {
                        "id": job_id,
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "now": dispatched_at,
                        "payload_json": request_json,
                    },
                )
            conn.execute(
                text(
                    """
                    UPDATE airank_retest_observation_windows
                    SET status='sampling', compare_run_id=:compare_run_id,
                        result_json=:result_json, updated_at=:now
                    WHERE tenant_id=:tenant_id AND id=:window_id AND status='scheduled'
                    """
                ),
                {
                    "compare_run_id": compare_run_id,
                    "result_json": json.dumps(
                        {
                            "contract_version": "airank.retest-dispatch.v1",
                            "baseline_run_id": baseline_run_id,
                            "compare_run_id": compare_run_id,
                            "task_count": len(frozen_tasks),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "now": dispatched_at,
                    "tenant_id": tenant_id,
                    "window_id": window_id,
                },
            )
            self._audit(
                conn,
                tenant_id=tenant_id,
                project_id=project_id,
                window_id=window_id,
                event_type="retest.scan_dispatched",
                payload={
                    "baseline_run_id": baseline_run_id,
                    "compare_run_id": compare_run_id,
                    "task_count": len(frozen_tasks),
                    "prompt_source": "baseline_task_request_json",
                },
                now=dispatched_at,
            )
            return RetestDispatchRecord(
                window_id,
                "scan_dispatched",
                compare_run_id,
                len(frozen_tasks),
                len(frozen_tasks),
            )

    def _block_window(
        self,
        conn: Any,
        *,
        window_id: str,
        tenant_id: str,
        project_id: str,
        now: datetime,
        error_code: str,
    ) -> RetestDispatchRecord:
        result = {
            "contract_version": "airank.retest-dispatch.v1",
            "error_code": error_code,
            "retryable": False,
        }
        conn.execute(
            text(
                """
                UPDATE airank_retest_observation_windows
                SET status='blocked', result_json=:result_json, updated_at=:now
                WHERE tenant_id=:tenant_id AND id=:window_id AND status='scheduled'
                """
            ),
            {
                "result_json": json.dumps(result, ensure_ascii=False, sort_keys=True),
                "now": now,
                "tenant_id": tenant_id,
                "window_id": window_id,
            },
        )
        self._audit(
            conn,
            tenant_id=tenant_id,
            project_id=project_id,
            window_id=window_id,
            event_type="retest.dispatch_blocked",
            payload=result,
            now=now,
        )
        return RetestDispatchRecord(window_id, "blocked", None, 0, 0, error_code)

    def _audit(
        self,
        conn: Any,
        *,
        tenant_id: str,
        project_id: str,
        window_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        now: datetime,
    ) -> None:
        event_id = _stable_id("audit_retest", tenant_id, window_id, event_type)
        insert_prefix = "INSERT OR IGNORE" if self.engine.dialect.name == "sqlite" else "INSERT IGNORE"
        conn.execute(
            text(
                f"""
                {insert_prefix} INTO airank_audit_events (
                  id, tenant_id, project_id, event_type, entity_type,
                  entity_id, actor_user_id, payload_json, created_at
                ) VALUES (
                  :id, :tenant_id, :project_id, :event_type, 'retest_window',
                  :entity_id, :actor_user_id, :payload_json, :created_at
                )
                """
            ),
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "event_type": event_type,
                "entity_id": window_id,
                "actor_user_id": self.scheduler_id,
                "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "created_at": now,
            },
        )

    def _scope_sql(self, alias: str) -> tuple[str, dict[str, object]]:
        clauses: list[str] = []
        params: dict[str, object] = {}
        if self.tenant_id:
            clauses.append(f"{alias}.tenant_id=:scope_tenant_id")
            params["scope_tenant_id"] = self.tenant_id
        if self.project_id:
            clauses.append(f"{alias}.project_id=:scope_project_id")
            params["scope_project_id"] = self.project_id
        if self.window_id:
            clauses.append(f"{alias}.id=:scope_window_id")
            params["scope_window_id"] = self.window_id
        return (" AND " + " AND ".join(clauses) if clauses else "", params)
