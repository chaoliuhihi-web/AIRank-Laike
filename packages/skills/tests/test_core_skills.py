from __future__ import annotations

from jsonschema import Draft202012Validator

from airank_skills import SKILL_RUNNERS, load_default_registry, run_skill


CORE_SKILL_IDS = {
    "measurement.sample-runner",
    "measurement.answer-parser",
    "measurement.citation-extractor",
    "research.intent-miner",
    "knowledge.fact-builder",
    "governance.claim-verifier",
    "intervention.page-blueprint",
    "delivery.retest-report",
}


def assert_expected_subset(actual: object, expected: object) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, value in expected.items():
            assert key in actual
            assert_expected_subset(actual[key], value)
        return
    if isinstance(expected, list):
        assert actual == expected
        return
    assert actual == expected


def test_registry_contains_versioned_core_skills_with_complete_contracts() -> None:
    registry = load_default_registry()
    manifests = registry.list()

    assert {manifest.skill_id for manifest in manifests} == CORE_SKILL_IDS
    assert set(SKILL_RUNNERS) == CORE_SKILL_IDS
    assert {manifest.status for manifest in manifests} == {"partial"}
    for manifest in manifests:
        assert manifest.version == "1.0.0"
        assert manifest.fact_policy
        assert manifest.failure_policy
        assert manifest.quality_rubric
        assert manifest.eval_cases
        assert manifest.entrypoint.endswith(SKILL_RUNNERS[manifest.skill_id].__name__)


def test_every_manifest_eval_case_executes_real_code_and_matches_output_schema() -> None:
    registry = load_default_registry()

    for manifest in registry.list():
        input_validator = Draft202012Validator(manifest.input_schema)
        output_validator = Draft202012Validator(manifest.output_schema)
        for case in manifest.eval_cases:
            input_validator.validate(case["input"])
            output = run_skill(manifest.skill_id, dict(case["input"]))
            output_validator.validate(output)
            assert_expected_subset(output, case["expected"])


def test_sample_runner_creates_independent_sessions_for_each_repeat() -> None:
    output = run_skill(
        "measurement.sample-runner",
        {
            "questions": ["企业 GEO 工具有哪些？"],
            "providers": ["qianwen", "doubao"],
            "surfaces": ["api"],
            "cohort_type": "blind",
            "repetitions": 3,
        },
    )

    assert output["task_count"] == 6
    assert len({task["session_id"] for task in output["tasks"]}) == 6
    assert {task["sample_index"] for task in output["tasks"]} == {1, 2, 3}


def test_retest_report_blocks_non_comparable_cohorts() -> None:
    output = run_skill(
        "delivery.retest-report",
        {
            "baseline": {
                "cohort_type": "blind",
                "provider_scope": ["qianwen"],
                "collector_surfaces": ["api"],
                "question_version": "v1",
            },
            "followup": {
                "cohort_type": "assisted",
                "provider_scope": ["qianwen"],
                "collector_surfaces": ["api"],
                "question_version": "v1",
            },
        },
    )

    assert output["status"] == "blocked"
    assert output["failure_code"] == "NON_COMPARABLE_WINDOWS"
