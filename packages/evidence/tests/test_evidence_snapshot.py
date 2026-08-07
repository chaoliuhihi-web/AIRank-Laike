from __future__ import annotations

from datetime import datetime, timezone

from airank_evidence import EvidenceSnapshot


def test_evidence_snapshot_hash_detects_raw_response_mutation() -> None:
    raw = {"provider": "qianwen", "answer_text": "原始回答", "citations": []}
    snapshot = EvidenceSnapshot.create(
        id="evidence_1",
        tenant_id="tenant_1",
        project_id="project_1",
        answer_snapshot_id="snap_1",
        raw_response=raw,
        captured_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
    )

    assert snapshot.verify_integrity() is True
    raw["answer_text"] = "外部字典被修改"
    assert snapshot.verify_integrity() is True
    object.__setattr__(snapshot, "raw_response_json", '{"answer_text":"篡改"}')
    assert snapshot.verify_integrity() is False
