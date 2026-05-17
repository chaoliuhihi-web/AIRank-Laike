from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.provider_scan import browser_provider_config, parse_provider_answer, provider_execution_mode, strip_prompt_echo


def test_browser_provider_config_uses_persistent_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIRANK_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("AIRANK_BROWSER_HEADLESS", "1")
    monkeypatch.delenv("AIRANK_CHATGPT_WEB_URL", raising=False)

    config = browser_provider_config("chatgpt")

    assert config.url == "https://chatgpt.com/"
    assert config.profile_dir == (tmp_path / "profiles" / "chatgpt").resolve()
    assert config.headless is True
    assert config.profile_dir.exists()
    assert config.public_metadata()["provider"] == "chatgpt"


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


def test_provider_answer_parser_falls_back_to_text_order() -> None:
    parsed = parse_provider_answer("建议优先考虑竞品甲，其次可以了解星河卓越。", "星河卓越", ["竞品甲"])

    assert parsed["brand_mentioned"] is True
    assert parsed["brand_rank"] == 2
    assert parsed["competitor_mentions"] == [{"name": "竞品甲", "mentioned": True, "rank": None}]


def test_strip_prompt_echo_removes_user_prompt_before_parsing_answer() -> None:
    prompt = "星河卓越是否值得选择？请在回答里给出你认为这些品牌的推荐排序，并说明原因。"
    page_delta = f"最近对话\n{prompt}\n综合推荐排序：\n1. 火山引擎\n2. 星河卓越"

    assert strip_prompt_echo(page_delta, prompt) == "综合推荐排序：\n1. 火山引擎\n2. 星河卓越"
