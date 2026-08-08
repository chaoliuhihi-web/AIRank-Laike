from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from airank_skills import SKILL_RUNNERS, build_promotion_ledger, evaluate_registry, load_default_registry, run_skill
from airank_skills.evaluation import file_sha256, load_verified_promotion_evidence


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
        expected_version = {
            "research.intent-miner": "1.2.0",
            "intervention.page-blueprint": "1.1.0",
        }.get(manifest.skill_id, "1.0.0")
        assert manifest.version == expected_version
        assert manifest.fact_policy
        assert manifest.failure_policy
        assert manifest.quality_rubric
        assert manifest.eval_cases
        assert manifest.promotion_policy["required_suites"] == ["contract", "holdout", "adversarial"]
        assert manifest.promotion_policy["minimum_pass_rate"] == 1.0
        assert manifest.promotion_policy["required_evidence"]
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


def test_intent_miner_normalizes_duplicates_and_keeps_competitors_out_of_blind() -> None:
    output = run_skill(
        "research.intent-miner",
        {
            "seed_questions": [
                "企业怎么选 GEO？",
                "企业怎么选GEO!",
                "竞品甲是否适合制造企业？",
            ],
            "target_names": ["AIRank"],
            "competitor_names": ["竞品甲"],
        },
    )

    assert output["question_count"] == 2
    assert output["questions"][0]["cohort_type"] == "blind"
    assert output["questions"][1]["cohort_type"] == "comparison"


def test_intent_miner_requires_observation_reference_before_marking_query_observed() -> None:
    output = run_skill(
        "research.intent-miner",
        {
            "seed_questions": ["企业怎么选择 GEO 平台？"],
            "observed_questions": [
                {
                    "question_text": "制造企业怎么选择 GEO 平台？",
                    "source_ref": "observation:qobatch_abcdef0123456789abcd:qobs_1234567890abcdef1234",
                    "evidence_grade": "user_provided_snapshot",
                    "occurrence_count": 6,
                    "observed_at": "2026-08-01T00:00:00Z",
                    "region": "江苏",
                },
                {
                    "question_text": "伪造观察问题？",
                    "source_ref": "manual:unverified",
                    "evidence_grade": "user_provided_snapshot",
                    "occurrence_count": 99,
                },
            ],
        },
    )

    assert output["question_count"] == 2
    observed = output["questions"][0]
    assert observed["source_kind"] == "observed_query"
    assert observed["observed_query"] is True
    assert observed["provenance_records"][0]["occurrence_count"] == 6
    assert all(item["question_text"] != "伪造观察问题?" for item in output["questions"])


def test_page_blueprint_binds_every_claim_to_exact_source_evidence() -> None:
    fact_text = "AIRank 支持私有化部署。"
    output = run_skill(
        "intervention.page-blueprint",
        {
            "asset_type": "faq",
            "title": "AIRank 部署能力 FAQ",
            "direction": "不得把这段编辑说明复制到正文",
            "facts": [
                {
                    "fact_id": "fact_1",
                    "revision_id": "revision_1",
                    "title": "部署能力",
                    "fact_text": fact_text,
                    "status": "approved",
                    "eligible_for_generation": True,
                    "support_ids": ["support_1"],
                    "evidence": [
                        {
                            "source_id": "source_1",
                            "source_sha256": "a" * 64,
                            "source_start": 12,
                            "source_end": 12 + len(fact_text),
                            "quoted_text": fact_text,
                        }
                    ],
                }
            ],
        },
    )

    assert output["status"] == "draft"
    assert output["skill_version"] == "1.1.0"
    assert output["blueprint_sha256"]
    assert output["title"] == "部署能力｜事实问答页"
    assert "AIRank 部署能力 FAQ" not in output["body_md"]
    assert output["claim_bindings"] == [
        {
            "claim_text": fact_text,
            "claim_sha256": output["claim_bindings"][0]["claim_sha256"],
            "fact_id": "fact_1",
            "fact_revision_id": "revision_1",
            "support_ids": ["support_1"],
            "source_id": "source_1",
            "source_sha256": "a" * 64,
            "source_start": 12,
            "source_end": 12 + len(fact_text),
        }
    ]
    assert "不得把这段编辑说明复制到正文" not in output["body_md"]
    assert output["structured_data"]["@type"] == "FAQPage"
    assert all(section["fact_revision_ids"] for section in output["sections"])
    assert all(section["support_ids"] for section in output["sections"])


def test_page_blueprint_rejects_invalid_source_boundary_without_generating_prose() -> None:
    output = run_skill(
        "intervention.page-blueprint",
        {
            "asset_type": "fact_page",
            "title": "事实页",
            "facts": [
                {
                    "fact_id": "fact_2",
                    "revision_id": "revision_2",
                    "fact_text": "事实正文",
                    "status": "approved",
                    "eligible_for_generation": True,
                    "support_ids": ["support_2"],
                    "evidence": [
                        {
                            "source_id": "source_2",
                            "source_sha256": "b" * 64,
                            "source_start": 0,
                            "source_end": 2,
                            "quoted_text": "事实正文",
                        }
                    ],
                }
            ],
        },
    )

    assert output["status"] == "needs_evidence"
    assert output["body_md"] == ""
    assert output["sections"] == []
    assert output["missing_fact_ids"] == ["fact_2"]
    assert output["missing_evidence"][0]["reasons"] == ["exact_source_boundary_missing"]


def test_page_blueprint_requires_an_editorial_brief_title() -> None:
    output = run_skill(
        "intervention.page-blueprint",
        {
            "asset_type": "fact_page",
            "title": "",
            "facts": [],
        },
    )

    assert output["status"] == "needs_evidence"
    assert any("title_missing" in item["reasons"] for item in output["missing_evidence"])


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


def test_every_core_skill_passes_contract_holdout_and_adversarial_suites() -> None:
    reports = evaluate_registry()

    assert len(reports) == 8
    assert sum(report.total_cases for report in reports) == 24
    assert all(report.local_eval_status == "passed" for report in reports)
    assert all(report.passed_cases == report.total_cases == 3 for report in reports)
    assert all(set(report.executed_suites) == {"contract", "holdout", "adversarial"} for report in reports)
    assert all(not report.promotion_eligible for report in reports)
    assert all(
        any(blocker.startswith("missing_promotion_evidence:") for blocker in report.promotion_blockers)
        for report in reports
    )


def test_promotion_evidence_requires_a_real_repository_artifact_hash(tmp_path) -> None:
    registry_path = Path(__file__).resolve().parents[1] / "registry.json"
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "evidence_version": "1.0.0",
                "evidence": [
                    {
                        "skill_id": "measurement.answer-parser",
                        "evidence_type": "reviewed_labeled_benchmark",
                        "artifact_path": "packages/skills/registry.json",
                        "sha256": file_sha256(registry_path),
                    },
                    {
                        "skill_id": "measurement.citation-extractor",
                        "evidence_type": "provider_citation_benchmark",
                        "artifact_path": "packages/skills/registry.json",
                        "sha256": "0" * 64,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    verified = load_verified_promotion_evidence(evidence_path)

    assert verified == {"measurement.answer-parser": {"reviewed_labeled_benchmark"}}


def test_promotion_ledger_is_content_addressed_and_retains_unproven_skills() -> None:
    ledger = build_promotion_ledger()

    assert set(ledger["source_sha256"]) == {
        "registry",
        "eval_corpus",
        "promotion_evidence",
        "implementation",
        "evaluation_engine",
    }
    assert all(len(value) == 64 for value in ledger["source_sha256"].values())
    assert {item["decision"] for item in ledger["skills"]} == {"retain_partial"}
