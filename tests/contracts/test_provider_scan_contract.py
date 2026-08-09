from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

import pytest

from apps.api.main import scan_dispatch_mode
from apps.api.provider_scan import (
    BrowserProbeError,
    BrowserProviderConfig,
    ProviderCallError,
    browser_provider_config,
    begin_fresh_conversation,
    build_brand_rank_prompt,
    call_api_provider_for_brand_rank,
    call_provider_for_brand_rank,
    classify_login_blocker,
    classify_provider_call_failure,
    is_login_input,
    looks_login_blocked,
    parse_provider_answer,
    probe_provider_generation_readiness,
    provider_execution_mode,
    strip_prompt_echo,
)
from airank_provider_gateway import (
    ProviderCitation,
    ProviderGatewayError,
    ProviderResult,
    ProviderUsage,
    UsagePrecision,
)


class FakeLocator:
    def __init__(self, attrs: dict[str, str | None]) -> None:
        self.attrs = attrs

    def get_attribute(self, attr_name: str, timeout: int = 500) -> str | None:
        return self.attrs.get(attr_name)


class FakeConversationCandidate:
    def __init__(self) -> None:
        self.clicked = False

    def is_visible(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return True

    def click(self) -> None:
        self.clicked = True


class FakeConversationLocator:
    def __init__(self, candidate: FakeConversationCandidate | None) -> None:
        self.candidate = candidate

    def count(self) -> int:
        return 1 if self.candidate else 0

    def nth(self, _index: int) -> FakeConversationCandidate:
        assert self.candidate is not None
        return self.candidate


class FakeConversationPage:
    def __init__(self, candidate: FakeConversationCandidate | None) -> None:
        self.url = "https://provider.example.test/"
        self.candidate = candidate

    def locator(self, selector: str) -> FakeConversationLocator:
        return FakeConversationLocator(
            self.candidate if selector == "button:has-text('新建对话')" else None
        )

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


def test_consumer_browser_requires_verified_new_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = FakeConversationCandidate()
    monkeypatch.setattr("apps.api.provider_scan.find_prompt_input", lambda _page: object())

    isolation = begin_fresh_conversation(FakeConversationPage(candidate))

    assert isolation["verified"] is True
    assert isolation["method"] == "new_conversation_control"
    assert candidate.clicked is True


def test_consumer_browser_blocks_when_new_conversation_cannot_be_verified() -> None:
    with pytest.raises(RuntimeError, match="fresh conversation could not be verified"):
        begin_fresh_conversation(FakeConversationPage(None))


def test_consumer_browser_classifies_login_url_before_sampling() -> None:
    page = FakeConversationPage(None)
    page.url = "https://provider.example.test/sign_in"

    with pytest.raises(RuntimeError, match="requires login"):
        begin_fresh_conversation(page)


def test_slider_verification_is_classified_as_captcha() -> None:
    challenge = "亲，请拖动下方滑块完成验证，通过验证以确保正常访问"

    assert looks_login_blocked(challenge) is True
    assert classify_login_blocker(challenge) == "captcha_required"


def test_captcha_failure_preserves_browser_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AIRANK_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(
        "apps.api.provider_scan.run_browser_probe",
        lambda _config, _prompt: {
            "trace_id": "browser:qianwen:captcha",
            "page_url": "https://www.qianwen.com/chat/captcha",
            "title": "千问",
            "answer_text": "亲，请拖动下方滑块完成验证",
            "screenshot_path": "/tmp/qianwen-captcha.png",
            "screenshot_sha256": "a" * 64,
            "source_links": [],
            "source_panel_status": "not_present",
            "source_panel_screenshot_path": "",
            "source_panel_screenshot_sha256": "",
            "source_panel_capture_mode": "visible_page_inspected_no_sources",
            "conversation_isolation": {
                "verified": True,
                "method": "new_conversation_control",
            },
        },
    )

    with pytest.raises(ProviderCallError) as raised:
        call_provider_for_brand_rank(
            provider="qianwen",
            brand_name="AIRank",
            website_url="https://airank.example",
            industry="GEO",
            competitor_names=[],
            question_text="企业应该如何选择 GEO 监测服务商？",
            cohort_type="blind",
            session_id="session_captcha",
            prompt_version_id="prompt_captcha",
        )

    assert raised.value.error_code == "CAPTCHA_REQUIRED"
    assert raised.value.retryable is False
    assert raised.value.public_metadata["screenshot_sha256"] == "a" * 64
    assert raised.value.public_metadata["conversation_isolation"]["verified"] is True


def test_release_generation_probe_requires_substantive_consumer_answer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "browser")
    monkeypatch.setenv("AIRANK_BROWSER_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(
        "apps.api.provider_scan.run_browser_probe",
        lambda _config, _prompt: {
            "answer_text": "证据需要保留原始回答、请求元数据、截图、引用来源和不可变哈希。" * 4,
            "page_url": "https://www.qianwen.com/chat/probe",
            "screenshot_path": "/tmp/qianwen-ready.png",
        },
    )

    result = probe_provider_generation_readiness("qianwen")

    assert result.status == "ready"
    assert result.probe_level == "l3_generation"
    assert result.generation_verified is True
    assert result.reason == "L3 consumer generation probe returned a substantive answer"


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


def test_provider_execution_mode_supports_real_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRANK_PROVIDER_MODE", "api")

    assert provider_execution_mode() == "api"


def test_scan_dispatch_defaults_to_durable_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRANK_SCAN_DISPATCH_MODE", raising=False)

    assert scan_dispatch_mode() == "worker"


def test_scan_dispatch_only_allows_explicit_inline_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRANK_SCAN_DISPATCH_MODE", "inline")
    assert scan_dispatch_mode() == "inline"

    monkeypatch.setenv("AIRANK_SCAN_DISPATCH_MODE", "unexpected")
    assert scan_dispatch_mode() == "worker"


def test_api_provider_scan_preserves_provider_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 8, 8, tzinfo=timezone.utc)

    class FakeGateway:
        def generate(self, provider: str, prompt: str, *, request_context=None) -> ProviderResult:
            assert provider == "qianwen"
            assert prompt == "企业 GEO 工具有哪些？"
            assert request_context.tenant_id == "__system__"
            assert request_context.idempotency_key.startswith("direct:session_1:")
            return ProviderResult(
                provider="qianwen",
                model="qwen-test",
                answer_text="可选方案包括 AIRank。",
                request_id="request_real_1",
                requested_at=now,
                completed_at=now,
                duration_ms=15,
                attempt_count=1,
                evidence_grade="provider_api_with_web_search",
                web_search_requested=True,
                web_search_used=True,
                citations=(
                    ProviderCitation(
                        url="https://example.com/a",
                        title="来源 A",
                        native_type="web_search_call_source",
                        source_path="/output/0/action/sources/0",
                        source_id="source_a",
                    ),
                ),
                usage=ProviderUsage(total_tokens=10, precision=UsagePrecision.EXACT),
                raw_response={"id": "request_real_1"},
                endpoint_host="dashscope.example.com",
                configuration_fingerprint="a" * 64,
                route_id="qianwen-primary",
                search_evidence="airank.provider-search-evidence.v1:explicit_tool_call",
                citation_parser_version="airank.provider-native-citation.v2",
            )

    monkeypatch.setattr("apps.api.provider_scan.get_api_gateway", lambda: FakeGateway())
    result = call_api_provider_for_brand_rank(
        provider="qianwen",
        brand_name="AIRank",
        website_url="https://airank.example",
        industry="GEO",
        competitor_names=[],
        question_text="企业 GEO 工具有哪些？",
        cohort_type="blind",
        session_id="session_1",
        prompt_version_id="prompt_v_1",
    )

    assert result.external_trace_id == "request_real_1"
    assert result.brand_mentioned is True
    assert result.native_citations[0]["url"] == "https://example.com/a"
    assert result.native_citations[0]["native_type"] == "web_search_call_source"
    assert result.native_citations[0]["source_path"] == "/output/0/action/sources/0"
    assert result.native_citations[0]["source_id"] == "source_a"
    assert result.raw_metadata["evidence_level"] == "provider_api_with_web_search"
    assert result.raw_metadata["provider_raw_response"] == {"id": "request_real_1"}
    assert result.raw_metadata["route_id"] == "qianwen-primary"
    assert result.raw_metadata["search_evidence"].endswith(":explicit_tool_call")
    assert result.raw_metadata["citation_parser_version"] == "airank.provider-native-citation.v2"
    assert result.raw_metadata["native_citation_count"] == 1


def test_api_provider_empty_answer_preserves_upstream_response_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upstream = {
        "id": "request_empty_1",
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "", "reasoning_content": "still reasoning"},
            }
        ],
    }

    class FakeSettings:
        model = "kimi-k3"
        endpoint_host = "api.moonshot.cn"

        @staticmethod
        def configuration_fingerprint(_provider: str) -> str:
            return "f" * 64

    class FakeGateway:
        @staticmethod
        def generate(_provider: str, _prompt: str, *, request_context=None) -> ProviderResult:
            raise ProviderGatewayError(
                "kimi",
                "PROVIDER_EMPTY_RESPONSE",
                "provider returned an empty answer",
                raw_response=upstream,
                provider_request_id="request_empty_1",
                duration_ms=1234,
                attempt_count=1,
                usage=ProviderUsage(total_tokens=4096, precision=UsagePrecision.EXACT),
                route_id="kimi:default",
                configuration_fingerprint="f" * 64,
                endpoint_host="api.moonshot.cn",
                model="kimi-k3",
                request_contract={
                    "max_tokens": 4096,
                    "max_tokens_field": "max_completion_tokens",
                    "temperature": None,
                    "reasoning_effort": "low",
                },
            )

        @staticmethod
        def settings(_provider: str) -> FakeSettings:
            return FakeSettings()

    monkeypatch.setattr("apps.api.provider_scan.get_api_gateway", lambda: FakeGateway())

    with pytest.raises(ProviderCallError) as captured:
        call_api_provider_for_brand_rank(
            provider="kimi",
            brand_name="AIRank",
            website_url="https://airank.example",
            industry="GEO",
            competitor_names=[],
            question_text="企业 GEO 工具有哪些？",
            cohort_type="blind",
            session_id="session_empty_1",
            prompt_version_id="prompt_v_1",
        )

    metadata = captured.value.public_metadata
    assert metadata["provider_request_id"] == "request_empty_1"
    assert metadata["provider_raw_response"] == upstream
    assert metadata["duration_ms"] == 1234
    assert metadata["attempt_count"] == 1
    assert metadata["usage"]["total_tokens"] == 4096
    assert metadata["request_contract"]["reasoning_effort"] == "low"


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


def test_provider_answer_parser_maps_competitor_alias_to_frozen_canonical_entity() -> None:
    parsed = parse_provider_answer(
        "推荐排序：\n1. AIRank\n2. 火山",
        "AIRank",
        ["火山引擎"],
        competitor_aliases={"火山引擎": ["火山"]},
    )

    assert parsed["competitor_mentions"] == [
        {"name": "火山引擎", "mentioned": True, "rank": 2, "matched_names": ["火山"]}
    ]


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
    assert result.raw_metadata["source_panel_status"] == "not_inspected"


def test_browser_failure_preserves_screenshot_and_prompt_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = BrowserProviderConfig(
        provider="doubao",
        label="豆包",
        url="https://www.doubao.com/chat/",
        profile_dir=tmp_path,
        headless=True,
        timeout_seconds=30,
        channel=None,
        executable_path=None,
    )
    monkeypatch.setattr("apps.api.provider_scan.browser_provider_config", lambda provider: config)
    monkeypatch.setattr(
        "apps.api.provider_scan.run_browser_probe",
        lambda _config, _prompt: (_ for _ in ()).throw(
            BrowserProbeError(
                "豆包 web page requires login or human verification; screenshot=/tmp/private.png",
                screenshot_path="/tmp/private.png",
                screenshot_sha256="b" * 64,
                page_url="https://www.doubao.com/chat/",
                page_title="豆包",
                trace_id="browser:doubao:failure-1",
            )
        ),
    )

    with pytest.raises(ProviderCallError) as caught:
        call_provider_for_brand_rank(
            provider="doubao",
            brand_name="AIRank",
            website_url="https://airank.example",
            industry="GEO",
            competitor_names=[],
            question_text="企业 GEO 工具有哪些？",
            cohort_type="blind",
            session_id="session_failure_1",
            prompt_version_id="prompt_v_1",
        )

    error = caught.value
    assert "screenshot=" not in error.reason
    assert error.public_metadata["screenshot_path"] == "/tmp/private.png"
    assert error.public_metadata["screenshot_sha256"] == "b" * 64
    assert error.public_metadata["session_id"] == "session_failure_1"
    assert error.public_metadata["prompt_version_id"] == "prompt_v_1"
    assert error.public_metadata["prompt_sha256"]
    assert error.public_metadata["browser_trace_id"] == "browser:doubao:failure-1"
    assert error.public_metadata["source_panel_status"] == "not_inspected"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ProviderCallError("qianwen", "provider network request failed", error_code="PROVIDER_NETWORK_FAILED"), ("SCAN_PROVIDER_FAILED", False)),
        (ProviderCallError("qianwen", "provider request failed", error_code="PROVIDER_AUTH_FAILED"), ("SCAN_PROVIDER_BLOCKED", True)),
        (ProviderCallError("qianwen", "provider request failed", error_code="PROVIDER_RATE_OR_QUOTA_LIMITED"), ("SCAN_PROVIDER_BLOCKED", True)),
        (ProviderCallError("doubao", "web answer did not appear before timeout", public_metadata={"capture_mode": "consumer_browser"}), ("SCAN_PROVIDER_TIMEOUT", False)),
        (ProviderCallError("doubao", "web page requires login", public_metadata={"capture_mode": "consumer_browser"}), ("SCAN_PROVIDER_BLOCKED", True)),
    ],
)
def test_provider_failure_classification_keeps_failed_and_blocked_separate(
    error: ProviderCallError,
    expected: tuple[str, bool],
) -> None:
    assert classify_provider_call_failure(error) == expected


def test_strip_prompt_echo_removes_user_prompt_before_parsing_answer() -> None:
    prompt = "星河卓越是否值得选择？请在回答里给出你认为这些品牌的推荐排序，并说明原因。"
    page_delta = f"最近对话\n{prompt}\n综合推荐排序：\n1. 火山引擎\n2. 星河卓越"

    assert strip_prompt_echo(page_delta, prompt) == "综合推荐排序：\n1. 火山引擎\n2. 星河卓越"


def test_login_placeholder_is_not_treated_as_prompt_input() -> None:
    locator = FakeLocator({"placeholder": "请登录后输入内容", "type": None})

    assert is_login_input(locator) is True
