from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Mapping

from airank_domain.measurement import sha256_text


@dataclass(frozen=True)
class EvidenceSnapshot:
    id: str
    tenant_id: str
    project_id: str
    answer_snapshot_id: str
    raw_response_json: str
    raw_response_sha256: str
    captured_at: datetime
    screenshot_ref_id: str | None = None
    source_panel_ref_id: str | None = None
    request_metadata: Mapping[str, Any] | None = None

    @classmethod
    def create(
        cls,
        *,
        id: str,
        tenant_id: str,
        project_id: str,
        answer_snapshot_id: str,
        raw_response: Mapping[str, Any],
        captured_at: datetime,
        screenshot_ref_id: str | None = None,
        source_panel_ref_id: str | None = None,
        request_metadata: Mapping[str, Any] | None = None,
    ) -> "EvidenceSnapshot":
        raw_response_json = json.dumps(
            raw_response, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        )
        return cls(
            id=id,
            tenant_id=tenant_id,
            project_id=project_id,
            answer_snapshot_id=answer_snapshot_id,
            raw_response_json=raw_response_json,
            raw_response_sha256=sha256_text(raw_response_json),
            captured_at=captured_at,
            screenshot_ref_id=screenshot_ref_id,
            source_panel_ref_id=source_panel_ref_id,
            request_metadata=dict(request_metadata or {}),
        )

    def verify_integrity(self) -> bool:
        return sha256_text(self.raw_response_json) == self.raw_response_sha256

    @property
    def raw_response(self) -> dict[str, Any]:
        return json.loads(self.raw_response_json)
