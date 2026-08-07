from __future__ import annotations

from airank_domain import (
    TAXONOMY_VERSION,
    compile_question_candidates,
    govern_question,
    question_dedupe_sha256,
)


def test_question_normalization_deduplicates_unicode_spacing_and_punctuation() -> None:
    assert question_dedupe_sha256(" 企业怎么选 GEO？ ") == question_dedupe_sha256("企业怎么选GEO!")


def test_taxonomy_separates_blind_comparison_and_fact_verification() -> None:
    blind = govern_question("企业应该如何选择 GEO 平台？", target_names=("AIRank",))
    comparison = govern_question(
        "AIRank 和竞品甲有什么区别？",
        target_names=("AIRank",),
        competitor_names=("竞品甲",),
    )
    fact = govern_question("AIRank 是否支持证据追溯？", target_names=("AIRank",))

    assert blind.cohort_type == "blind"
    assert blind.question_type == "select"
    assert comparison.cohort_type == "comparison"
    assert fact.cohort_type == "fact_verification"
    assert fact.intent_level == "high"
    assert fact.buyer_stage == "decision"
    assert fact.prompt_style == "factual"
    assert {blind.taxonomy_version, comparison.taxonomy_version, fact.taxonomy_version} == {TAXONOMY_VERSION}


def test_blind_cohort_excludes_competitor_named_prompts() -> None:
    competitor_prompt = govern_question(
        "竞品甲是否适合制造企业？",
        target_names=("AIRank",),
        competitor_names=("竞品甲",),
        source_ref="seed:competitor",
    )

    assert competitor_prompt.cohort_type == "comparison"


def test_compiler_marks_templates_as_candidates_and_never_invents_observed_volume() -> None:
    map_id, input_sha256, questions = compile_question_candidates(
        brand_name="AIRank",
        company_names=("星河科技",),
        product_terms=("GEO 平台",),
        competitor_names=("竞品甲",),
        regions=("北京",),
        seed_questions=("GEO 平台多少钱？", " GEO平台多少钱! "),
        include_template_candidates=True,
    )

    assert map_id.startswith("question_map_")
    assert len(input_sha256) == 64
    assert len([item for item in questions if item["source_kind"] == "provided_seed"]) == 1
    assert any(item["cohort_type"] == "comparison" for item in questions)
    assert all("volume" not in item and item["observed_query"] is False for item in questions)
    assert all(item["question_version_id"].startswith("question_v_") for item in questions)
