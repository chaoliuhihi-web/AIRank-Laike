from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from airank_evidence import ObjectStorageError
from apps.api.main import (
    persist_provider_failure_screenshot,
    persist_provider_screenshot,
    persist_provider_source_panel,
)
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


def test_visible_source_panel_capture_is_persisted_as_a_distinct_evidence_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_path = tmp_path / "source-panel.png"
    capture_payload = b"visible provider source panel"
    capture_path.write_bytes(capture_payload)
    capture_sha256 = hashlib.sha256(capture_payload).hexdigest()
    durable_root = tmp_path / "durable-objects"
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "filesystem")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(durable_root))

    stored = persist_provider_source_panel(
        "tenant_1",
        "project_1",
        provider_result(
            {
                "source_panel_status": "captured",
                "source_panel_screenshot_path": str(capture_path),
                "source_panel_screenshot_sha256": capture_sha256,
            }
        ),
    )

    assert stored is not None
    assert stored.sha256 == capture_sha256
    assert "/provider-source-panel/" in stored.key


def test_source_panel_not_present_does_not_create_an_object() -> None:
    assert persist_provider_source_panel(
        "tenant_1",
        "project_1",
        provider_result({"source_panel_status": "not_present"}),
    ) is None


def test_browser_failure_screenshot_is_copied_to_immutable_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capture_path = tmp_path / "blocked-browser.png"
    capture_payload = b"browser login blocker evidence"
    capture_path.write_bytes(capture_payload)
    capture_sha256 = hashlib.sha256(capture_payload).hexdigest()
    durable_root = tmp_path / "durable-objects"
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_DRIVER", "filesystem")
    monkeypatch.setenv("AIRANK_OBJECT_STORAGE_ROOT", str(durable_root))

    stored = persist_provider_failure_screenshot(
        "tenant_1",
        "project_1",
        {
            "provider_metadata": {
                "screenshot_path": str(capture_path),
                "screenshot_sha256": capture_sha256,
            }
        },
    )

    assert stored is not None
    assert stored.sha256 == capture_sha256
    assert "/provider-failure-screenshot/" in stored.key
    capture_path.unlink()
    assert Path(stored.uri.removeprefix("file://")).read_bytes() == capture_payload


def test_partial_failure_screenshot_metadata_is_rejected() -> None:
    with pytest.raises(ObjectStorageError, match="both path and SHA-256"):
        persist_provider_failure_screenshot(
            "tenant_1",
            "project_1",
            {"provider_metadata": {"screenshot_path": "/tmp/blocked.png"}},
        )
