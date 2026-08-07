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
