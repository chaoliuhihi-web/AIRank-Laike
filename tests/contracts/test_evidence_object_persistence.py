from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from airank_evidence import ObjectStorageError
from apps.api.main import persist_provider_screenshot
from apps.api.provider_scan import ProviderScanResult


def provider_result(raw_metadata: dict[str, object]) -> ProviderScanResult:
    return ProviderScanResult(
        provider="doubao",
        provider_label="豆包",
        answer_text="真实回答",
        brand_mentioned=False,
        brand_rank=None,
        competitor_mentions=[],
        sentiment="neutral",
        mention_class="not_mentioned",
        target_entity_mentions=[],
        confidence=None,
        external_trace_id="provider-request-id",
        native_citations=[],
        raw_metadata=raw_metadata,
    )


def test_browser_screenshot_is_copied_out_of_temporary_capture_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_path = tmp_path / "temporary-capture.png"
    capture_payload = b"browser screenshot evidence"
    capture_path.write_bytes(capture_payload)
    capture_sha256 = hashlib.sha256(capture_payload).hexdigest()
    durable_root = tmp_path / "durable-objects"
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "filesystem")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(durable_root))

    stored = persist_provider_screenshot(
        "tenant_1",
        "project_1",
        provider_result(
            {
                "screenshot_path": str(capture_path),
                "screenshot_sha256": capture_sha256,
            }
        ),
    )

    assert stored is not None
    assert stored.sha256 == capture_sha256
    assert stored.uri != capture_path.resolve().as_uri()
    assert Path(stored.uri.removeprefix("file://")).read_bytes() == capture_payload
    capture_path.unlink()
    assert Path(stored.uri.removeprefix("file://")).read_bytes() == capture_payload


def test_partial_screenshot_metadata_is_rejected() -> None:
    with pytest.raises(ObjectStorageError, match="both screenshot path and SHA-256"):
        persist_provider_screenshot(
            "tenant_1",
            "project_1",
            provider_result({"screenshot_path": "/tmp/capture.png"}),
        )
