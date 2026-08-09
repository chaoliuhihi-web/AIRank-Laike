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
    "knowledge.entity-graph-compiler",
    "governance.claim-verifier",
    "intervention.page-blueprint",
    "intervention.explainer-builder",
    "intervention.comparison-builder",
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


def test_entity_graph_compiler_excludes_ambiguous_alias_without_touching_evidence() -> None:
    evidence_hash = "a" * 64
    output = run_skill(
        "knowledge.entity-graph-compiler",
        {
            "entities": [
                {"entity_id": "target", "entity_role": "target", "entity_kind": "brand", "canonical_name": "AIRank", "fact_revision_id": "rev_1", "fact_eligible": True, "evidence_manifest_sha256": evidence_hash},
                {"entity_id": "peer", "entity_role": "competitor", "entity_kind": "brand", "canonical_name": "竞品", "fact_revision_id": "rev_2", "fact_eligible": True, "evidence_manifest_sha256": evidence_hash},
            ],
            "aliases": [
                {"alias_id": "alias_1", "entity_id": "target", "alias_text": "星河", "fact_revision_id": "rev_1", "fact_eligible": True, "evidence_manifest_sha256": evidence_hash},
                {"alias_id": "alias_2", "entity_id": "peer", "alias_text": "星河", "fact_revision_id": "rev_2", "fact_eligible": True, "evidence_manifest_sha256": evidence_hash},
            ],
            "relations": [],
        },
    )

    assert output["status"] == "partial"
    assert output["ambiguous_aliases"][0]["excluded_from_measurement"] is True
    assert all(item["ambiguous"] is True for item in output["graph"]["aliases"])
    assert output["raw_evidence_mutated"] is False


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


def test_page_blueprint_forces_comparison_through_specialized_builder() -> None:
    fact_text = "AIRank 支持私有化部署。"
    output = run_skill(
        "intervention.page-blueprint",
        {
            "asset_type": "comparison_page",
            "title": "对比页",
            "facts": [
                {
                    "fact_id": "fact_1",
                    "revision_id": "revision_1",
                    "fact_text": fact_text,
                    "status": "approved",
                    "eligible_for_generation": True,
                    "support_ids": ["support_1"],
                    "evidence": [{"source_id": "source_1", "source_sha256": "a" * 64, "source_start": 0, "source_end": len(fact_text), "quoted_text": fact_text}],
                }
            ],
        },
    )

    assert output["status"] == "needs_evidence"
    assert output["body_md"] == ""
    assert any("comparison_builder_required" in item["reasons"] for item in output["missing_evidence"])


def comparison_skill_input() -> dict[str, object]:
    subjects = [
        {"subject_id": "subject_airank", "display_name": "AIRank", "subject_type": "brand"},
        {"subject_id": "subject_peer", "display_name": "竞品甲", "subject_type": "competitor"},
    ]
    dimensions = [
        {"dimension_id": f"dimension_{index}", "label": f"核验维度 {index}"}
        for index in range(1, 11)
    ]
    facts = []
    for subject in subjects:
        for dimension in dimensions:
            fact_text = f"{subject['display_name']} 在{dimension['label']}下的已核验事实。"
            revision_id = f"revision_{subject['subject_id']}_{dimension['dimension_id']}"
            facts.append(
                {
                    "fact_id": f"fact_{subject['subject_id']}_{dimension['dimension_id']}",
                    "revision_id": revision_id,
                    "subject_id": subject["subject_id"],
                    "subject_type": subject["subject_type"],
                    "subject_ref_id": subject["subject_id"],
                    "dimension_id": dimension["dimension_id"],
                    "fact_text": fact_text,
                    "status": "approved",
                    "eligible_for_generation": True,
                    "support_ids": [f"support_{revision_id}"],
                    "evidence": [
                        {
                            "source_id": f"source_{revision_id}",
                            "source_sha256": "c" * 64,
                            "source_start": 5,
                            "source_end": 5 + len(fact_text),
                            "quoted_text": fact_text,
                        }
                    ],
                }
            )
    return {
        "title": "不得直接复制到正文的比较 brief",
        "direction": "保持公平，不输出排名",
        "target_subject_id": "subject_airank",
        "subjects": subjects,
        "dimensions": dimensions,
        "facts": facts,
    }


def test_comparison_builder_requires_symmetric_subject_dimension_evidence() -> None:
    payload = comparison_skill_input()
    output = run_skill("intervention.comparison-builder", payload)

    assert output["status"] == "draft"
    assert output["skill_version"] == "1.0.0"
    assert output["fairness"] == {
        "same_scope": True,
        "subject_count": 2,
        "dimension_count": 10,
        "required_cell_count": 20,
        "covered_cell_count": 20,
        "coverage_rate": 1.0,
        "ranking_or_score_generated": False,
    }
    assert len(output["sections"]) == 10
    assert len(output["claim_bindings"]) == 20
    assert "不得直接复制到正文的比较 brief" not in output["body_md"]
    assert "排名" in output["body_md"]
    assert all(binding["subject_id"] and binding["dimension_id"] for binding in output["claim_bindings"])


def test_comparison_builder_blocks_missing_cell_and_subject_relabeling() -> None:
    payload = comparison_skill_input()
    payload["facts"] = list(payload["facts"][:-1])
    payload["facts"][0] = {**payload["facts"][0], "subject_ref_id": "subject_peer"}
    output = run_skill("intervention.comparison-builder", payload)

    assert output["status"] == "needs_evidence"
    assert output["body_md"] == ""
    reasons = {reason for item in output["missing_evidence"] for reason in item["reasons"]}
    assert "fact_subject_binding_mismatch" in reasons
    assert "symmetric_evidence_cell_missing" in reasons


def explainer_skill_input() -> dict[str, object]:
    roles = ["definition", "mechanism", "mechanism", "step", "step", "step", "criterion", "criterion", "misconception", "faq", "faq", "boundary"]
    facts = []
    for index, role in enumerate(roles, start=1):
        fact_text = f"第{index}条已审核说明：" + "该事实基于当前有效来源的精确原文边界，用于解释适用范围、执行条件与验证方式，不扩展为来源之外的承诺。" * 3
        facts.append(
            {
                "fact_id": f"fact_{index}",
                "revision_id": f"revision_{index}",
                "title": f"解释证据 {index}",
                "subject_type": "brand",
                "subject_ref_id": "subject_airank",
                "content_role": role,
                "fact_text": fact_text,
                "status": "approved",
                "eligible_for_generation": True,
                "support_ids": [f"support_{index}"],
                "evidence": [{"source_id": f"source_{index}", "source_sha256": "e" * 64, "source_start": 10, "source_end": 10 + len(fact_text), "quoted_text": fact_text}],
            }
        )
    return {
        "title": "不进入公开正文的解释 brief",
        "direction": "面向采购者完整解释",
        "subject_id": "subject_airank",
        "subject_type": "brand",
        "display_name": "AIRank",
        "brand_names": ["AIRank", "来客"],
        "facts": facts,
    }


def test_explainer_builder_enforces_role_length_and_exact_evidence_gates() -> None:
    output = run_skill("intervention.explainer-builder", explainer_skill_input())

    assert output["status"] == "draft"
    assert output["skill_version"] == "1.0.0"
    assert output["quality"]["accepted_fact_count"] == 12
    assert output["quality"]["supported_character_count"] >= 1400
    assert output["quality"]["brand_mention_count"] == 0
    assert all(item["complete"] for item in output["quality"]["role_coverage"].values())
    assert len(output["sections"]) == 7
    assert len(output["claim_bindings"]) == 12
    assert output["structured_data"]["@graph"][0]["@type"] == "HowTo"
    assert output["structured_data"]["@graph"][1]["@type"] == "FAQPage"
    assert "不进入公开正文的解释 brief" not in output["body_md"]


def test_explainer_builder_blocks_brand_stuffing_without_generating_prose() -> None:
    payload = explainer_skill_input()
    facts = list(payload["facts"])
    for index in range(4):
        fact_text = f"AIRank {facts[index]['fact_text']}"
        facts[index] = {
            **facts[index],
            "fact_text": fact_text,
            "evidence": [{**facts[index]["evidence"][0], "source_end": 10 + len(fact_text), "quoted_text": fact_text}],
        }
    payload["facts"] = facts
    output = run_skill("intervention.explainer-builder", payload)

    assert output["status"] == "needs_evidence"
    assert output["body_md"] == ""
    assert output["quality"]["brand_mention_count"] == 4
    assert any("brand_mention_limit_exceeded" in item["reasons"] for item in output["missing_evidence"])


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

    assert len(reports) == len(CORE_SKILL_IDS)
    assert sum(report.total_cases for report in reports) == len(CORE_SKILL_IDS) * 3
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
