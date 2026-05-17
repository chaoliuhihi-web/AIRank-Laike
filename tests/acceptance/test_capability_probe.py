from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "xinghe-adapter" / "src"))

from airank_xinghe_adapter import CapabilityProbe, CapabilityStatus, ProbeConfig  # noqa: E402


def test_capability_probe_acceptance_dev_only_matrix() -> None:
    config = ProbeConfig.from_env(
        {
            "AIRANK_AUTH_MODE": "dev",
            "AIRANK_OBJECT_STORAGE_DRIVER": "local",
            "AIRANK_OBJECT_STORAGE_ROOT": ".runtime/objects",
        }
    )

    results = CapabilityProbe(
        config,
        now=datetime(2026, 5, 17, 9, 30, tzinfo=timezone.utc),
    ).run()
    matrix = {result.capability: result.to_record() for result in results}

    assert matrix["yudao_auth"]["status"] == CapabilityStatus.DEV_ONLY
    assert matrix["yudao_tenant_user"]["status"] == CapabilityStatus.DEV_ONLY
    assert matrix["object_storage"]["status"] == CapabilityStatus.DEV_ONLY
    assert matrix["xinghe_hermes"]["status"] == CapabilityStatus.DEV_ONLY
    assert matrix["xinghe_crawler_gateway"]["fallback"] == "packages/crawler-lite"
