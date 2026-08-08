from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_fact_acquisition_requires_governed_gap_and_approved_facts() -> None:
    route_source = (ROOT / "apps/api/fact_acquisition_routes.py").read_text(encoding="utf-8")
    migration_source = (
        ROOT / "apps/api/alembic/versions/20260809_0032_fact_acquisition_tasks.py"
    ).read_text(encoding="utf-8")
    web_source = (ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")

    for marker in (
        'TASK_CONTRACT_VERSION = "airank.fact-acquisition-task.v1"',
        'GAP_CONTRACT_VERSION = "airank.evidence-gap.v2"',
        'AUTHORITY_POLICY = "official_or_verified_third_party.v1"',
        '"FACT_ACQUISITION_GAP_INELIGIBLE"',
        '"FACT_ACQUISITION_EVIDENCE_INVALID"',
        'resolution_state = "ready_for_intervention" if all_eligible else "needs_fact_review"',
        "_revision_is_eligible",
        "previous_event_sha256",
        "event_sha256",
    ):
        assert marker in route_source

    assert "airank_fact_acquisition_tasks" in migration_source
    assert "airank_fact_acquisition_task_events" in migration_source
    assert "uk_airank_fact_acquisition_event_version" in migration_source
    assert 'data-testid="fact-acquisition-task-list"' in web_source
    assert "补证任务完成不等于内容已生成或已发布" in web_source
