from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from airank_xinghe_adapter import CapabilityProbe, CapabilityStatus, ProbeConfig
from airank_xinghe_adapter import capability as capability_module
from airank_xinghe_adapter.capability import parse_timeout_seconds


NOW = datetime(2026, 5, 17, 9, 0, tzinfo=timezone.utc)


def test_probe_reports_dev_only_for_local_fallbacks_without_tokens() -> None:
    config = ProbeConfig.from_env(
        {
            "AIRANK_AUTH_MODE": "yudao",
            "YUDAO_PERMISSION_INFO_URL": "http://127.0.0.1:48080/admin-api/system/auth/get-permission-info",
            "AIRANK_OBJECT_STORAGE_DRIVER": "local",
            "AIRANK_OBJECT_STORAGE_ROOT": ".runtime/objects",
        }
    )

    results = {result.capability: result for result in CapabilityProbe(config, now=NOW).run()}

    assert results["yudao_auth"].status == CapabilityStatus.DEV_ONLY
    assert results["yudao_tenant_user"].status == CapabilityStatus.DEV_ONLY
    assert results["object_storage"].status == CapabilityStatus.DEV_ONLY
    assert results["xinghe_hermes"].status == CapabilityStatus.DEV_ONLY
    assert results["xinghe_crawler_gateway"].fallback == "packages/crawler-lite"


def test_probe_can_report_ready_and_partial_external_capabilities() -> None:
    config = ProbeConfig.from_env(
        {
            "AIRANK_AUTH_MODE": "yudao",
            "YUDAO_PERMISSION_INFO_URL": "http://yudao.local/permission",
            "YUDAO_BEARER_TOKEN": "token",
            "YUDAO_TENANT_ID": "1",
            "XINGHE_CRAWLER_GATEWAY_BASE_URL": "http://crawler.local",
            "XINGHE_HERMES_BASE_URL": "http://hermes.local",
        }
    )

    def fake_http(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if "yudao" in url:
            assert headers["Authorization"] == "Bearer token"
            assert headers["tenant-id"] == "1"
            return 200, '{"code":0,"data":{"tenant_id":"tenant_1","user_id":"user_1"}}'
        if "crawler" in url:
            return 503, "starting"
        if "hermes" in url:
            raise TimeoutError("not reachable")
        return 200, "{}"

    results = {
        result.capability: result
        for result in CapabilityProbe(config, http_probe=fake_http, now=NOW).run()
    }

    assert results["yudao_auth"].status == CapabilityStatus.READY
    assert results["yudao_tenant_user"].status == CapabilityStatus.READY
    assert results["xinghe_crawler_gateway"].status == CapabilityStatus.PARTIAL
    assert results["xinghe_hermes"].status == CapabilityStatus.PARTIAL


def test_probe_reports_ready_for_writable_filesystem_object_storage(tmp_path: Path) -> None:
    storage_root = tmp_path / "objects"
    config = ProbeConfig.from_env(
        {
            "AIRANK_AUTH_MODE": "dev",
            "AIRANK_OBJECT_STORAGE_DRIVER": "filesystem",
            "AIRANK_OBJECT_STORAGE_ROOT": str(storage_root),
        }
    )

    results = {result.capability: result for result in CapabilityProbe(config, now=NOW).run()}

    assert results["object_storage"].status == CapabilityStatus.READY
    assert results["object_storage"].metadata["probe"] == "write-read-delete"


def test_probe_reports_ready_for_verified_s3_object_storage(monkeypatch) -> None:
    objects: dict[str, bytes] = {}

    class FakeStorage:
        def put_bytes(self, payload: bytes, *, key: str, content_type: str):
            del content_type
            objects[key] = payload
            return type("Stored", (), {"byte_size": len(payload)})()

        def get_bytes(self, key: str) -> bytes:
            return objects[key]

        def delete(self, key: str) -> None:
            objects.pop(key, None)

    monkeypatch.setattr(capability_module, "build_object_storage_from_env", lambda _env: FakeStorage())
    config = ProbeConfig.from_env(
        {
            "AIRANK_OBJECT_STORAGE_DRIVER": "s3",
            "AIRANK_S3_ENDPOINT_URL": "https://object-storage.example.com",
            "AIRANK_S3_BUCKET": "airank-evidence",
            "AIRANK_S3_ACCESS_KEY_ID": "access-key",
            "AIRANK_S3_SECRET_ACCESS_KEY": "secret-key",
        }
    )

    results = {result.capability: result for result in CapabilityProbe(config, now=NOW).run()}

    assert results["object_storage"].status == CapabilityStatus.READY
    assert results["object_storage"].metadata == {
        "driver": "s3",
        "bucket": "airank-evidence",
        "probe": "write-read-delete",
    }
    assert objects == {}


def test_probe_config_reads_positive_timeout_from_env() -> None:
    config = ProbeConfig.from_env({"AIRANK_PROBE_TIMEOUT_SECONDS": "3.5"})

    assert config.timeout_seconds == 3.5
    assert config.auth_mode == "yudao"
    assert parse_timeout_seconds("0") == 0.3
    assert parse_timeout_seconds("bad") == 0.3


def test_probe_blocks_yudao_http_200_when_business_code_fails() -> None:
    config = ProbeConfig.from_env(
        {
            "AIRANK_AUTH_MODE": "yudao",
            "YUDAO_PERMISSION_INFO_URL": "http://yudao.local/permission",
            "YUDAO_BEARER_TOKEN": "token",
        }
    )

    def fake_http(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
        return 200, '{"code":401,"msg":"账号未登录","data":null}'

    results = {
        result.capability: result
        for result in CapabilityProbe(config, http_probe=fake_http, now=NOW).run()
    }

    assert results["yudao_auth"].status == CapabilityStatus.BLOCKED
    assert "business code is not 0" in results["yudao_auth"].blocked_reason
    assert results["yudao_tenant_user"].status == CapabilityStatus.BLOCKED
