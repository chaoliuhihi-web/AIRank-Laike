from __future__ import annotations

from pathlib import Path

from apps.api.main import build_scan_metrics


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_does_not_emit_demo_business_metrics_without_evidence() -> None:
    metrics = build_scan_metrics(task_count=12, provider_count=4)

    assert metrics["data_status"] == "unverified_no_provider_evidence"
    assert metrics["provider_success_count"] == 0
    assert "ai_visibility_score" not in metrics
    assert "monthly_leads" not in metrics


def test_provider_runtime_keeps_valid_not_mentioned_answers() -> None:
    source = (ROOT / "apps" / "api" / "provider_scan.py").read_text(encoding="utf-8")

    assert "web page did not return an answer mentioning" not in source
    assert '"confidence": 0.72 if brand_mentioned else 0.58' not in source
    assert "positions.sort" not in source


def test_api_runtime_does_not_create_fake_provider_citations_or_demo_metrics() -> None:
    source = (ROOT / "apps" / "api" / "main.py").read_text(encoding="utf-8")

    forbidden = (
        'source_type": "provider_answer"',
        'label="本月 AI 来客线索"',
        'name="示例科技有限公司"',
        'value="72"',
        'value="68"',
        'value="18"',
        'value="96"',
    )
    for snippet in forbidden:
        assert snippet not in source


def test_measurement_migration_contains_version_repeat_and_immutable_evidence_fields() -> None:
    migration = (
        ROOT / "apps" / "api" / "alembic" / "versions" / "20260808_0003_measurement_credibility.py"
    ).read_text(encoding="utf-8")

    required = (
        "airank_prompt_versions",
        "cohort_type",
        "prompt_version_id",
        "sample_index",
        "session_id",
        "collector_surface",
        "evidence_level",
        "sample_status",
        "mention_class",
        "target_entity_mentions_json",
        "answer_sha256",
        "raw_response_sha256",
        "airank_evidence_snapshots",
    )
    for field in required:
        assert field in migration
