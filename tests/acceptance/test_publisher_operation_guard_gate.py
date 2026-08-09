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


def test_publisher_reconciliation_is_read_only_and_never_force_resolves() -> None:
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
