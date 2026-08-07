from __future__ import annotations

from datetime import datetime, timezone

import pytest

from airank_domain.measurement import BrandEntity, PromptCohortType, PromptVersion, find_entity_mentions


NOW = datetime(2026, 8, 8, tzinfo=timezone.utc)


def test_prompt_version_is_content_addressed() -> None:
    first = PromptVersion.create(
        cohort_type=PromptCohortType.BLIND,
        prompt_text="企业 GEO 平台有哪些？",
        target_entity="AIRank",
        created_at=NOW,
    )
    second = PromptVersion.create(
        cohort_type=PromptCohortType.BLIND,
        prompt_text="企业 GEO 平台有哪些？",
        target_entity="AIRank",
        created_at=NOW,
    )

    assert first.prompt_version_id == second.prompt_version_id
    assert len(first.prompt_sha256) == 64


def test_blind_prompt_cannot_reveal_target_entity() -> None:
    with pytest.raises(ValueError, match="blind prompt"):
        PromptVersion.create(
            cohort_type=PromptCohortType.BLIND,
            prompt_text="AIRank 值得选择吗？",
            target_entity="AIRank",
            created_at=NOW,
        )


def test_brand_entity_recognizes_company_alias_and_product_without_changing_canonical_name() -> None:
    entity = BrandEntity(
        canonical_name="AIRank",
        aliases=("AI Rank",),
        company_names=("星河科技",),
        product_names=("来客",),
    )

    mentions = find_entity_mentions("星河科技推出的来客也叫 AI Rank。", entity)

    assert [mention.entity_type for mention in mentions] == ["company", "product", "alias"]
    assert {mention.canonical_name for mention in mentions} == {"AIRank"}
