from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_external_publisher_uses_persistent_operation_guard_and_fail_closed_unknown_state() -> None:
    migration = read("apps/api/alembic/versions/20260809_0043_publisher_operation_guard.py")
    worker = read("apps/worker/airank_worker/publisher.py")

    assert "operation_id" in migration
    assert "uk_airank_publish_attempt_operation" in migration
    assert "fk_airank_publish_attempt_operation" in migration
    assert "MySQLOperationGuard" in worker
    assert 'operation_type="publisher.publish"' in worker
    assert "before_external_effect" in worker
    assert "mark_outcome_unknown" in worker
    assert "automatic replay is forbidden" in worker
    assert '"PUBLISH_ATTEMPT_ABANDONED",' not in worker


def test_publisher_automatic_reconciliation_is_read_only_and_never_force_resolves() -> None:
    worker = read("apps/worker/airank_worker/publisher.py")
    api = read("apps/api/delivery_routes.py")
    console = read("apps/web/src/App.tsx")

    assert "def find_existing" in worker
    assert 'snapshot.channel != "wordpress"' in worker
    assert '"GET"' in worker
    assert '"POST"' in worker
    assert '"/publish-operations/{operation_id}"' in api
    assert "require_delivery_admin(permission_header)" in api
    assert "forbidden_unknown" in api
    assert "禁止自动重发" in console
    assert "force_success" not in worker
    assert "force_success" not in api


def test_manual_publication_reconciliation_requires_two_people_and_immutable_evidence() -> None:
    migration = read("apps/api/alembic/versions/20260809_0046_publication_reconciliation.py")
    reconciliation = read("apps/api/publication_reconciliation.py")
    console = read("apps/web/src/App.tsx")

    assert "airank_publish_reconciliation_cases" in migration
    assert "airank_publish_reconciliation_events" in migration
    assert "reconciliation_case_id" in migration
    assert 'Literal["succeeded"]' in reconciliation
    assert "PUBLISH_RECONCILIATION_SECOND_PERSON_REQUIRED" in reconciliation
    assert "build_object_storage_from_env" in reconciliation
    assert "sha256_bytes" in reconciliation
    assert '"external_delivery_verified": False' in reconciliation
    assert "transition_in_transaction" in reconciliation
    assert "实际 HTTP 状态码" in console
    assert "reconciliationResponseStatus" in console
    assert "responseStatus: 200" not in console
    assert "系统不提供“确认未发生并重发”选项" in console
    assert "force_success" not in reconciliation
    assert "not_applied" not in reconciliation


def test_publication_update_and_withdraw_preserve_lineage_and_fail_closed() -> None:
    migration = read("apps/api/alembic/versions/20260809_0045_publication_mutations.py")
    worker = read("apps/worker/airank_worker/publisher.py")
    api = read("apps/api/delivery_routes.py")

    for field in ("publication_action", "target_package_id", "action_reason", "requested_by"):
        assert field in migration
    assert "airank.publish-snapshot.v3" in api
    assert "mutation_request_sha256" in api
    assert "active_mutation_package_id" in api
    assert '"superseded" if snapshot.publication_action == "update" else "withdrawn"' in worker
    assert '"status": "draft"' in worker
    assert 'snapshot.publication_action == "publish"' in worker
    assert '"DELETE"' not in worker
