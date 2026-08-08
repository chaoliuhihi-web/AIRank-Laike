from __future__ import annotations

from pathlib import Path

from airank_provider_gateway import PROVIDER_MANIFESTS


ROOT = Path(__file__).resolve().parents[2]


def test_four_required_api_provider_manifests_are_explicitly_partial() -> None:
    assert set(PROVIDER_MANIFESTS) == {"doubao", "qianwen", "kimi", "deepseek"}
    for manifest in PROVIDER_MANIFESTS.values():
        assert manifest.implementation_status.value == "partial"
        assert manifest.collection_mode == "provider_api"
        assert manifest.endpoint_env
        assert manifest.key_env
        assert manifest.model_env


def test_provider_operations_migration_has_no_plaintext_credential_column() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0005_provider_gateway_operations.py"
    ).read_text(encoding="utf-8")

    required_tables = (
        "airank_provider_manifests",
        "airank_provider_probe_runs",
        "airank_provider_request_audits",
        "airank_provider_usage_events",
        "airank_provider_circuit_states",
        "airank_provider_quota_buckets",
        "airank_provider_quota_reservations",
    )
    for table in required_tables:
        assert table in migration
    assert "configuration_fingerprint" in migration
    assert "api_key VARCHAR" not in migration
    assert "secret VARCHAR" not in migration

    capacity_migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0015_provider_capacity_leases.py"
    ).read_text(encoding="utf-8")
    assert "airank_provider_capacity_states" in capacity_migration
    assert "airank_provider_capacity_leases" in capacity_migration
    assert "available_tokens" in capacity_migration
    assert "in_flight_count" in capacity_migration
    assert "api_key" not in capacity_migration

    route_migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0016_provider_routes.py"
    ).read_text(encoding="utf-8")
    assert "airank_provider_routes" in route_migration
    assert "route_id" in route_migration
    assert "airank_provider_request_audits" in route_migration
    assert "api_key" not in route_migration

    control_migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0017_provider_route_controls.py"
    ).read_text(encoding="utf-8")
    assert "airank_provider_route_controls" in control_migration
    assert "airank_provider_route_control_events" in control_migration
    assert "control_version" in control_migration
    assert "api_key" not in control_migration
    assert "secret" not in control_migration


def test_provider_runtime_uses_persisted_state_and_task_idempotency_context() -> None:
    provider_scan = (ROOT / "apps" / "api" / "provider_scan.py").read_text(encoding="utf-8")
    operations = (ROOT / "apps" / "api" / "provider_operations.py").read_text(encoding="utf-8")

    assert "MySQLProviderOperations(database_url)" in provider_scan
    assert "circuit_breaker=_API_PROVIDER_OPERATIONS" in provider_scan
    assert "quota_ledger=_API_PROVIDER_OPERATIONS" in provider_scan
    assert "capacity_ledger=_API_PROVIDER_OPERATIONS" in provider_scan
    assert "route_policy=_API_PROVIDER_OPERATIONS" in provider_scan
    assert "probe_sink=_API_PROVIDER_OPERATIONS.record_probe" in provider_scan
    assert 'f"scan:{tenant_id}:{project_id}:{task_id}"' in provider_scan
    assert "FOR UPDATE" in operations
    assert "PROVIDER_REQUEST_IN_PROGRESS" in operations
    assert "airank_provider_probe_runs" in operations
    assert "acquire_capacity" in operations
    assert "PROVIDER_DISTRIBUTED_RATE_LIMITED" in operations
    assert "PROVIDER_DISTRIBUTED_CONCURRENCY_LIMITED" in operations
    assert "resolve_provider_routes" in operations
    assert "airank_provider_routes" in operations
    assert "airank_provider_route_controls" in operations
    assert "airank_provider_route_control_events" in operations
    assert "PROVIDER_LAST_ROUTE_DISABLE_FORBIDDEN" in operations
    assert "api_key" not in operations
