from __future__ import annotations

from pathlib import Path

from apps.api.main import resolve_task_question_text


ROOT = Path(__file__).resolve().parents[2]


def test_worker_executes_frozen_task_prompt_before_mutable_question_text() -> None:
    assert (
        resolve_task_question_text(
            {
                "question_id": "question_1",
                "request_json": '{"question_text":"frozen prompt"}',
            },
            {"question_1": "edited prompt"},
            fallback="fallback prompt",
        )
        == "frozen prompt"
    )


def test_scheduler_clones_baseline_contract_and_requires_safe_scope() -> None:
    scheduler = (ROOT / "apps" / "scheduler" / "airank_scheduler" / "retest.py").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "apps" / "scheduler" / "airank_scheduler" / "main.py").read_text(
        encoding="utf-8"
    )
    worker = (ROOT / "apps" / "worker" / "airank_worker" / "main.py").read_text(
        encoding="utf-8"
    )

    assert "baseline_task_request_json" in scheduler
    assert "RETEST_FROZEN_PROMPT_MISSING" in scheduler
    assert "AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED" in main
    assert "AIRANK_WORKER_GLOBAL_SCOPE_ENABLED" in worker
    assert "--dry-run" in main and "--dry-run" in worker
