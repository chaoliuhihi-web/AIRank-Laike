from __future__ import annotations

from datetime import datetime, timezone

from airank_xinghe_adapter import CapabilityProbe, CapabilityStatus, ProbeConfig


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
            "XINGHE_CRAWLER_GATEWAY_BASE_URL": "http://crawler.local",
            "XINGHE_HERMES_BASE_URL": "http://hermes.local",
        }
    )

    def fake_http(url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if "yudao" in url:
            assert headers["Authorization"] == "Bearer token"
            return 200, '{"tenant_id":"tenant_1","user_id":"user_1"}'
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
