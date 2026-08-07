from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.provider_scan import (
    BrowserProviderConfig,
    browser_provider_config,
    build_brand_rank_prompt,
    call_provider_for_brand_rank,
    is_login_input,
    parse_provider_answer,
    provider_execution_mode,
    strip_prompt_echo,
)


class FakeLocator:
    def __init__(self, attrs: dict[str, str | None]) -> None:
        self.attrs = attrs

    def get_attribute(self, attr_name: str, timeout: int = 500) -> str | None:
        return self.attrs.get(attr_name)


def test_browser_provider_config_uses_persistent_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIRANK_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("AIRANK_BROWSER_HEADLESS", "1")
    monkeypatch.setenv("AIRANK_BROWSER_CHANNEL", "chrome")
    monkeypatch.setenv("AIRANK_BROWSER_EXECUTABLE_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    monkeypatch.delenv("AIRANK_CHATGPT_WEB_URL", raising=False)

    config = browser_provider_config("chatgpt")

    assert config.url == "https://chatgpt.com/"
    assert config.profile_dir == (tmp_path / "profiles" / "chatgpt").resolve()
    assert config.headless is True
    assert config.channel == "chrome"
    assert config.executable_path == "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    assert config.profile_dir.exists()
    assert config.public_metadata()["provider"] == "chatgpt"
    assert config.public_metadata()["channel"] == "chrome"


def test_provider_execution_mode_defaults_to_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRANK_PROVIDER_MODE", raising=False)

    assert provider_execution_mode() == "browser"


def test_provider_answer_parser_extracts_rank_from_browser_text() -> None:
    parsed = parse_provider_answer(
        """
        综合推荐排序：
        1. 星河卓越：更适合需要 AI 营销自动化快速落地的企业。
        2. 火山引擎：底层云和模型能力更强。
        """,
        "星河卓越",
        ["火山引擎"],
    )

    assert parsed["brand_mentioned"] is True
    assert parsed["brand_rank"] == 1
    assert parsed["sentiment"] == "positive"
    assert parsed["competitor_mentions"] == [{"name": "火山引擎", "mentioned": True, "rank": 2}]


def test_provider_answer_parser_does_not_infer_rank_from_text_order() -> None:
    parsed = parse_provider_answer("建议优先考虑竞品甲，其次可以了解星河卓越。", "星河卓越", ["竞品甲"])

    assert parsed["brand_mentioned"] is True
    assert parsed["brand_rank"] is None
    assert parsed["confidence"] is None
    assert parsed["competitor_mentions"] == [{"name": "竞品甲", "mentioned": True, "rank": None}]


def test_provider_answer_parser_recognizes_company_and_product_entities() -> None:
    parsed = parse_provider_answer(
        "星河科技的来客产品可以列入候选。",
        "AIRank",
        [],
        company_names=["星河科技"],
        product_names=["来客"],
    )

    assert parsed["brand_mentioned"] is True
    assert parsed["mention_class"] == "candidate"
    assert {item["entity_type"] for item in parsed["target_entity_mentions"]} == {"company", "product"}


def test_blind_prompt_does_not_inject_brand_or_competitors() -> None:
    prompt = build_brand_rank_prompt(
        "AIRank",
        "https://airank.example",
        "GEO",
        ["竞品甲"],
        "企业 GEO 工具有哪些？",
        cohort_type="blind",
    )

    assert prompt == "企业 GEO 工具有哪些？"
    assert "AIRank" not in prompt
    assert "竞品甲" not in prompt


def test_blind_prompt_rejects_company_or_product_leakage() -> None:
    with pytest.raises(ValueError, match="blind cohort"):
        build_brand_rank_prompt(
            "AIRank",
            "https://airank.example",
            "GEO",
            [],
            "星河科技的来客产品怎么样？",
            cohort_type="blind",
            company_names=["星河科技"],
            product_names=["来客"],
        )


def test_assisted_and_comparison_prompts_are_explicitly_separate() -> None:
    assisted = build_brand_rank_prompt(
        "AIRank", "https://airank.example", "GEO", ["竞品甲"], "这个产品适合谁？", cohort_type="assisted"
    )
    comparison = build_brand_rank_prompt(
        "AIRank", "https://airank.example", "GEO", ["竞品甲"], "如何选择？", cohort_type="comparison"
    )

    assert "AIRank" in assisted and "竞品甲" not in assisted
    assert "AIRank" in comparison and "竞品甲" in comparison


def test_valid_no_mention_answer_is_not_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = BrowserProviderConfig(
        provider="chatgpt",
        label="ChatGPT",
        url="https://chatgpt.com/",
        profile_dir=tmp_path,
        headless=True,
        timeout_seconds=30,
        channel=None,
        executable_path=None,
    )
    monkeypatch.setattr("apps.api.provider_scan.browser_provider_config", lambda provider: config)
    monkeypatch.setattr(
        "apps.api.provider_scan.run_browser_probe",
        lambda _config, _prompt: {
            "answer_text": "可以考虑甲平台和乙平台，分别适合不同规模的企业。",
            "trace_id": "trace_real",
            "page_url": "https://chatgpt.com/c/1",
            "title": "answer",
            "screenshot_path": "/tmp/evidence.png",
            "screenshot_sha256": "a" * 64,
            "source_links": [],
        },
    )

    result = call_provider_for_brand_rank(
        provider="chatgpt",
        brand_name="AIRank",
        website_url="https://airank.example",
        industry="GEO",
        competitor_names=["竞品甲"],
        question_text="企业 GEO 工具有哪些？",
        cohort_type="blind",
    )

    assert result.brand_mentioned is False
    assert result.mention_class == "not_mentioned"
    assert result.brand_rank is None


def test_strip_prompt_echo_removes_user_prompt_before_parsing_answer() -> None:
    prompt = "星河卓越是否值得选择？请在回答里给出你认为这些品牌的推荐排序，并说明原因。"
    page_delta = f"最近对话\n{prompt}\n综合推荐排序：\n1. 火山引擎\n2. 星河卓越"

    assert strip_prompt_echo(page_delta, prompt) == "综合推荐排序：\n1. 火山引擎\n2. 星河卓越"


def test_login_placeholder_is_not_treated_as_prompt_input() -> None:
    locator = FakeLocator({"placeholder": "请登录后输入内容", "type": None})

    assert is_login_input(locator) is True
