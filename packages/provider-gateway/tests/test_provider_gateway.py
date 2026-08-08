from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

import pytest

from airank_provider_gateway import (
    CircuitBreaker,
    HealthState,
    HttpResponse,
    InMemoryQuotaLedger,
    ProbeLevel,
    ProviderCapacityLease,
    ProviderGateway,
    ProviderGatewayError,
    ProviderSettings,
    ProviderRequestContext,
    ResolvedProviderRoute,
    UsagePrecision,
    canonical_provider,
    get_manifest,
)


class FakeTransport:
    def __init__(self, responses: list[HttpResponse | ProviderGatewayError]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.network_probe_count = 0

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, ProviderGatewayError):
            raise response
        return response

    def network_probe(self, endpoint: str, timeout_seconds: float) -> None:
        self.network_probe_count += 1


def qianwen_env() -> dict[str, str]:
    return {
        "QIANWEN_API_KEY": "secret-never-returned",
        "QIANWEN_API_URL": "https://dashscope.example.test/v1/chat/completions",
        "QIANWEN_MODEL": "qwen-test",
        "AIRANK_PROVIDER_QPS": "100",
        "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
    }


def test_alias_and_manifest_configuration_never_expose_plaintext_key() -> None:
    gateway = ProviderGateway(env=qianwen_env(), transport=FakeTransport([]))
    settings = gateway.settings("tongyi")

    assert canonical_provider("tongyi") == "qianwen"
    assert settings.configured is True
    assert "secret-never-returned" not in settings.configuration_fingerprint("qianwen")
    assert len(settings.configuration_fingerprint("qianwen")) == 64


def test_unapproved_custom_endpoint_is_not_treated_as_configured() -> None:
    env = qianwen_env()
    env.pop("AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS")
    gateway = ProviderGateway(env=env, transport=FakeTransport([]))

    assert gateway.settings("qianwen").configured is False
    with pytest.raises(ProviderGatewayError) as caught:
        gateway.generate("qianwen", "测试")
    assert caught.value.code == "PROVIDER_NOT_CONFIGURED"


def test_route_registry_falls_through_unconfigured_primary_without_exposing_keys() -> None:
    env = qianwen_env()
    env.update(
        {
            "QIANWEN_SECONDARY_KEY": "secondary-secret",
            "QIANWEN_ROUTES_JSON": """[
              {"route_id":"primary","priority":100,"endpoint":"https://primary.example.test/v1/chat/completions","model":"qwen-primary","key_env":"QIANWEN_PRIMARY_KEY"},
              {"route_id":"secondary","priority":50,"endpoint":"https://secondary.example.test/v1/chat/completions","model":"qwen-secondary","key_env":"QIANWEN_SECONDARY_KEY"}
            ]""",
        }
    )
    transport = FakeTransport(
        [HttpResponse(status=200, headers={}, data={"id": "req_secondary", "choices": [{"message": {"content": "OK"}}]})]
    )

    result = ProviderGateway(env=env, transport=transport).generate("qianwen", "测试")

    assert result.route_id == "secondary"
    assert result.model == "qwen-secondary"
    assert transport.calls[0]["url"] == "https://secondary.example.test/v1/chat/completions"
    assert "secondary-secret" not in result.configuration_fingerprint


def test_retryable_upstream_failure_fails_over_to_next_route_with_audit() -> None:
    env = qianwen_env()
    env.update(
        {
            "QIANWEN_PRIMARY_KEY": "primary-secret",
            "QIANWEN_SECONDARY_KEY": "secondary-secret",
            "QIANWEN_ROUTES_JSON": """[
              {"route_id":"primary","priority":100,"endpoint":"https://primary.example.test/v1/chat/completions","model":"qwen-primary","key_env":"QIANWEN_PRIMARY_KEY"},
              {"route_id":"secondary","priority":50,"endpoint":"https://secondary.example.test/v1/chat/completions","model":"qwen-secondary","key_env":"QIANWEN_SECONDARY_KEY"}
            ]""",
        }
    )
    transport = FakeTransport(
        [
            ProviderGatewayError(
                "qianwen", "PROVIDER_UPSTREAM_FAILED", "primary unavailable", retryable=True
            ),
            HttpResponse(status=200, headers={}, data={"id": "req_secondary", "choices": [{"message": {"content": "fallback"}}]}),
        ]
    )
    audits: list[Mapping[str, Any]] = []
    result = ProviderGateway(
        env=env,
        transport=transport,
        max_attempts=1,
        audit_sink=audits.append,
    ).generate("qianwen", "测试")

    assert [call["url"] for call in transport.calls] == [
        "https://primary.example.test/v1/chat/completions",
        "https://secondary.example.test/v1/chat/completions",
    ]
    assert result.answer_text == "fallback"
    assert result.route_id == "secondary"
    assert [audit["route_id"] for audit in audits] == ["primary", "secondary"]
    assert [audit["outcome"] for audit in audits] == ["failed", "success"]


def test_runtime_route_policy_can_disable_primary_without_restart() -> None:
    class DisablePrimaryPolicy:
        def apply_routes(
            self,
            provider: str,
            routes: tuple[ResolvedProviderRoute, ...],
        ) -> tuple[ResolvedProviderRoute, ...]:
            assert provider == "qianwen"
            return tuple(route for route in routes if route.route_id != "primary")

    env = qianwen_env()
    env.update(
        {
            "QIANWEN_PRIMARY_KEY": "primary-secret",
            "QIANWEN_SECONDARY_KEY": "secondary-secret",
            "QIANWEN_ROUTES_JSON": """[
              {"route_id":"primary","priority":100,"endpoint":"https://primary.example.test/v1/chat/completions","key_env":"QIANWEN_PRIMARY_KEY"},
              {"route_id":"secondary","priority":50,"endpoint":"https://secondary.example.test/v1/chat/completions","key_env":"QIANWEN_SECONDARY_KEY"}
            ]""",
        }
    )
    transport = FakeTransport(
        [HttpResponse(status=200, headers={}, data={"id": "req_secondary", "choices": [{"message": {"content": "OK"}}]})]
    )

    result = ProviderGateway(
        env=env,
        transport=transport,
        route_policy=DisablePrimaryPolicy(),
    ).generate("qianwen", "测试")

    assert result.route_id == "secondary"
    assert [call["url"] for call in transport.calls] == [
        "https://secondary.example.test/v1/chat/completions"
    ]


def test_runtime_route_policy_fails_closed_when_all_routes_are_disabled() -> None:
    class DisableAllPolicy:
        def apply_routes(
            self,
            provider: str,
            routes: tuple[ResolvedProviderRoute, ...],
        ) -> tuple[ResolvedProviderRoute, ...]:
            return ()

    with pytest.raises(ProviderGatewayError) as caught:
        ProviderGateway(
            env=qianwen_env(),
            transport=FakeTransport([]),
            route_policy=DisableAllPolicy(),
        ).generate("qianwen", "测试")

    assert caught.value.code == "PROVIDER_ROUTES_DISABLED_BY_CONTROL"


def test_global_tenant_quota_failure_cannot_be_bypassed_by_route_fallback() -> None:
    class ExhaustedQuotaLedger(InMemoryQuotaLedger):
        def reserve(self, provider: str, units: int = 1, *, context=None):
            raise ProviderGatewayError(
                provider, "PROVIDER_QUOTA_EXHAUSTED", "tenant quota exhausted"
            )

    env = qianwen_env()
    env["QIANWEN_ROUTES_JSON"] = """[
      {"route_id":"primary","priority":100},
      {"route_id":"secondary","priority":50}
    ]"""
    transport = FakeTransport([])
    with pytest.raises(ProviderGatewayError) as caught:
        ProviderGateway(
            env=env, transport=transport, quota_ledger=ExhaustedQuotaLedger()
        ).generate("qianwen", "测试")

    assert caught.value.code == "PROVIDER_QUOTA_EXHAUSTED"
    assert transport.calls == []


def test_route_configuration_rejects_inline_secret_material() -> None:
    env = qianwen_env()
    env["QIANWEN_ROUTES_JSON"] = """[
      {"route_id":"unsafe","priority":100,"api_key":"must-not-be-accepted"}
    ]"""

    with pytest.raises(ProviderGatewayError) as caught:
        ProviderGateway(env=env, transport=FakeTransport([])).generate("qianwen", "测试")

    assert caught.value.code == "PROVIDER_ROUTE_CONFIG_INVALID"


def test_qianwen_generation_preserves_request_id_search_evidence_citation_and_usage() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status=200,
                headers={"x-request-id": "req_qianwen_1"},
                data={
                    "choices": [{"message": {"content": "候选包括品牌甲。"}}],
                    "search_info": {
                        "sources": [
                            {
                                "type": "search_source",
                                "url": "https://example.com/source",
                                "title": "来源",
                            }
                        ]
                    },
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
                },
            )
        ]
    )
    audits: list[Mapping[str, Any]] = []
    gateway = ProviderGateway(
        env=qianwen_env(), transport=transport, audit_sink=audits.append, sleep=lambda _: None
    )

    result = gateway.generate("qianwen", "有哪些候选？")

    assert result.request_id == "req_qianwen_1"
    assert result.evidence_grade == "provider_api_with_web_search"
    assert result.web_search_used is True
    assert result.citations[0].url == "https://example.com/source"
    assert result.citations[0].native_type == "search_info_source"
    assert result.citations[0].source_path == "/search_info/sources/0"
    assert result.search_evidence.endswith(":explicit_search_info")
    assert result.usage.total_tokens == 20
    assert result.usage.precision == UsagePrecision.EXACT
    assert transport.calls[0]["payload"]["enable_search"] is True
    assert "Authorization" not in audits[0]
    assert audits[0]["request_id_present"] is True
    assert audits[0]["request_contract"] == {
        "request_kind": "chat_completions_search",
        "citation_parser_version": "airank.provider-native-citation.v2",
        "search_evidence_version": "airank.provider-search-evidence.v1",
        "max_tokens": 4096,
        "max_tokens_field": "max_tokens",
        "temperature": 0.2,
        "reasoning_effort": None,
    }


def test_doubao_responses_payload_and_output_parser() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status=200,
                headers={},
                data={
                    "id": "resp_doubao_1",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "豆包回答"}],
                        },
                        {
                            "type": "web_search_call",
                            "source": {"url": "https://example.cn/a", "title": "证据 A"},
                        },
                    ],
                    "usage": {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                },
            )
        ]
    )
    gateway = ProviderGateway(
        env={
            "DOUBAO_API_KEY": "secret",
            "DOUBAO_API_URL": "https://ark.example.test/api/v3/responses",
            "DOUBAO_MODEL": "doubao-test",
            "AIRANK_PROVIDER_QPS": "100",
            "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
        },
        transport=transport,
    )

    result = gateway.generate("doubao", "测试")

    assert result.answer_text == "豆包回答"
    assert result.request_id == "resp_doubao_1"
    assert result.web_search_used is True
    assert result.evidence_grade == "provider_api_with_web_search"
    assert result.citations[0].title == "证据 A"
    assert transport.calls[0]["payload"]["tools"] == [{"type": "web_search"}]


def test_kimi_k3_uses_official_reasoning_and_completion_contract() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status=200,
                headers={"x-request-id": "req_kimi_1"},
                data={"id": "req_kimi_1", "choices": [{"message": {"content": "Kimi 回答"}}]},
            )
        ]
    )
    env = {
        "KIMI_API_KEY": "secret",
        "KIMI_API_URL": "https://kimi.example.test/v1/chat/completions",
        "KIMI_MODEL": "kimi-k3",
        "AIRANK_PROVIDER_QPS": "100",
        "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
    }
    gateway = ProviderGateway(env=env, transport=transport)

    result = gateway.generate("kimi", "测试")

    assert result.answer_text == "Kimi 回答"
    assert transport.calls[0]["payload"]["max_completion_tokens"] == 4096
    assert "max_tokens" not in transport.calls[0]["payload"]
    assert "temperature" not in transport.calls[0]["payload"]
    assert transport.calls[0]["payload"]["reasoning_effort"] == "low"
    assert result.request_contract == {
        "request_kind": "chat_completions",
        "citation_parser_version": "airank.provider-native-citation.v2",
        "search_evidence_version": "airank.provider-search-evidence.v1",
        "max_tokens": 4096,
        "max_tokens_field": "max_completion_tokens",
        "temperature": None,
        "reasoning_effort": "low",
    }
    assert result.web_search_requested is False
    assert result.web_search_used is False
    assert result.search_evidence.endswith(":not_requested")
    default_fingerprint = gateway.settings("kimi").configuration_fingerprint("kimi")
    overridden = ProviderGateway(
        env={**env, "KIMI_REASONING_EFFORT": "high"},
        transport=FakeTransport([]),
    )
    assert overridden.settings("kimi").reasoning_effort == "high"
    assert overridden.settings("kimi").configuration_fingerprint("kimi") != default_fingerprint


def test_empty_provider_response_preserves_upstream_failure_evidence() -> None:
    upstream = {
        "id": "req_empty_1",
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "", "reasoning_content": "still reasoning"},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4096, "total_tokens": 4106},
    }
    transport = FakeTransport([HttpResponse(status=200, headers={}, data=upstream)])

    with pytest.raises(ProviderGatewayError) as captured:
        ProviderGateway(env=qianwen_env(), transport=transport).generate("qianwen", "测试")

    error = captured.value
    assert error.code == "PROVIDER_EMPTY_RESPONSE"
    assert error.provider_request_id == "req_empty_1"
    assert error.raw_response == upstream
    assert error.attempt_count == 1
    assert error.usage is not None
    assert error.usage.total_tokens == 4106
    assert error.request_contract == {
        "request_kind": "chat_completions_search",
        "citation_parser_version": "airank.provider-native-citation.v2",
        "search_evidence_version": "airank.provider-search-evidence.v1",
        "max_tokens": 4096,
        "max_tokens_field": "max_tokens",
        "temperature": 0.2,
        "reasoning_effort": None,
    }


def test_doubao_falls_back_without_search_when_account_has_not_opened_tool() -> None:
    transport = FakeTransport(
        [
            ProviderGatewayError(
                "doubao",
                "PROVIDER_MODEL_OR_ENDPOINT_NOT_FOUND",
                "tool unavailable",
                status_code=404,
                provider_code="ToolNotOpen",
            ),
            HttpResponse(
                status=200,
                headers={"x-request-id": "req_doubao_fallback"},
                data={
                    "id": "resp_doubao_fallback",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": "无联网回答"}]}],
                },
            ),
        ]
    )
    gateway = ProviderGateway(
        env={
            "DOUBAO_API_KEY": "secret",
            "DOUBAO_API_URL": "https://ark.example.test/api/v3/responses",
            "DOUBAO_MODEL": "doubao-test",
            "AIRANK_PROVIDER_QPS": "100",
            "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
        },
        transport=transport,
    )

    result = gateway.generate("doubao", "测试")

    assert transport.calls[0]["payload"]["tools"] == [{"type": "web_search"}]
    assert "tools" not in transport.calls[1]["payload"]
    assert result.answer_text == "无联网回答"
    assert result.web_search_requested is False
    assert result.web_search_used is False
    assert result.evidence_grade == "provider_api_search_not_used"
    assert result.search_evidence.endswith(":not_requested")


def test_qianwen_responses_route_extracts_only_native_action_sources() -> None:
    env = qianwen_env()
    env.update(
        {
            "QIANWEN_API_URL": "https://dashscope.example.test/v1/responses",
            "QIANWEN_REQUEST_KIND": "responses_web_search",
        }
    )
    transport = FakeTransport(
        [
            HttpResponse(
                status=200,
                headers={"x-request-id": "req_qwen_responses"},
                data={
                    "id": "req_qwen_responses",
                    "output": [
                        {
                            "type": "web_search_call",
                            "action": {
                                "sources": [
                                    {
                                        "id": "source_1",
                                        "url": "https://official.example/source",
                                        "title": "官方来源",
                                    }
                                ]
                            },
                        },
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "联网回答"}
                            ],
                        },
                    ],
                    "debug": {
                        "references": [
                            {"url": "https://must-not-count.example/debug"}
                        ]
                    },
                },
            )
        ]
    )

    result = ProviderGateway(env=env, transport=transport).generate(
        "qianwen", "查询最新资料"
    )

    assert transport.calls[0]["payload"]["tools"] == [{"type": "web_search"}]
    assert transport.calls[0]["payload"]["max_output_tokens"] == 4096
    assert "messages" not in transport.calls[0]["payload"]
    assert result.web_search_requested is True
    assert result.web_search_used is True
    assert result.search_evidence.endswith(":explicit_tool_call")
    assert [citation.url for citation in result.citations] == [
        "https://official.example/source"
    ]
    assert result.citations[0].source_path == "/output/0/action/sources/0"
    assert result.citations[0].source_id == "source_1"
    assert result.request_contract["request_kind"] == "responses_web_search"


def test_route_request_kind_is_validated_and_changes_configuration_fingerprint() -> None:
    chat_gateway = ProviderGateway(env=qianwen_env(), transport=FakeTransport([]))
    responses_env = {
        **qianwen_env(),
        "QIANWEN_REQUEST_KIND": "responses_web_search",
        "QIANWEN_API_URL": "https://dashscope.example.test/v1/responses",
    }
    responses_gateway = ProviderGateway(env=responses_env, transport=FakeTransport([]))

    assert chat_gateway.settings("qianwen").request_kind == "chat_completions_search"
    assert responses_gateway.settings("qianwen").request_kind == "responses_web_search"
    assert (
        chat_gateway.settings("qianwen").configuration_fingerprint("qianwen")
        != responses_gateway.settings("qianwen").configuration_fingerprint("qianwen")
    )

    invalid = qianwen_env()
    invalid["QIANWEN_ROUTES_JSON"] = """[
      {"route_id":"invalid","request_kind":"unknown_protocol"}
    ]"""
    with pytest.raises(ProviderGatewayError) as caught:
        ProviderGateway(env=invalid, transport=FakeTransport([])).generate(
            "qianwen", "测试"
        )
    assert caught.value.code == "PROVIDER_ROUTE_CONFIG_INVALID"

    invalid_env = qianwen_env()
    invalid_env["QIANWEN_REQUEST_KIND"] = "unknown_protocol"
    with pytest.raises(ProviderGatewayError) as env_caught:
        ProviderGateway(env=invalid_env, transport=FakeTransport([])).settings("qianwen")
    assert env_caught.value.code == "PROVIDER_REQUEST_KIND_INVALID"


def test_legacy_openai_chat_manifest_kind_normalizes_to_public_contract() -> None:
    manifest = replace(get_manifest("qianwen"), request_kind="openai_chat")

    settings = ProviderSettings.from_env(manifest, {"QIANWEN_API_KEY": "test-key"})

    assert settings.request_kind == "chat_completions"


def test_retryable_failure_retries_and_circuit_opens() -> None:
    failures = [
        ProviderGatewayError("qianwen", "PROVIDER_UPSTREAM_FAILED", "upstream", retryable=True),
        ProviderGatewayError("qianwen", "PROVIDER_UPSTREAM_FAILED", "upstream", retryable=True),
    ]
    circuit = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
    gateway = ProviderGateway(
        env=qianwen_env(),
        transport=FakeTransport(failures),
        max_attempts=2,
        circuit_breaker=circuit,
        sleep=lambda _: None,
    )

    with pytest.raises(ProviderGatewayError, match="upstream"):
        gateway.generate("qianwen", "测试")
    with pytest.raises(ProviderGatewayError) as caught:
        gateway.generate("qianwen", "测试")
    assert caught.value.code == "PROVIDER_CIRCUIT_OPEN"


def test_circuit_state_isolated_by_configuration_fingerprint() -> None:
    circuit = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)

    circuit.failure("qianwen", "a" * 64, retryable=True)

    assert circuit.allow("qianwen", "a" * 64) is False
    assert circuit.allow("qianwen", "b" * 64) is True


def test_gateway_passes_tenant_idempotency_context_to_quota_ledger() -> None:
    class CapturingLedger(InMemoryQuotaLedger):
        context: ProviderRequestContext | None = None

        def reserve(self, provider: str, units: int = 1, *, context=None):
            self.context = context
            return super().reserve(provider, units, context=context)

    ledger = CapturingLedger()
    transport = FakeTransport(
        [HttpResponse(status=200, headers={}, data={"id": "req_context", "choices": [{"message": {"content": "OK"}}]})]
    )
    gateway = ProviderGateway(env=qianwen_env(), transport=transport, quota_ledger=ledger)
    context = ProviderRequestContext(tenant_id="tenant_1", project_id="project_1", idempotency_key="task_1")

    gateway.generate("qianwen", "测试", request_context=context)

    assert ledger.context == context


def test_gateway_holds_distributed_capacity_around_provider_call() -> None:
    class CapturingCapacityLedger:
        context: ProviderRequestContext | None = None
        released_lease: ProviderCapacityLease | None = None

        def acquire_capacity(self, provider, configuration_fingerprint, *, context):
            self.context = context
            return ProviderCapacityLease(
                provider=provider,
                configuration_fingerprint=configuration_fingerprint,
                tenant_id=context.tenant_id,
            )

        def release_capacity(self, lease):
            lease.released = True
            self.released_lease = lease

    capacity = CapturingCapacityLedger()
    transport = FakeTransport(
        [HttpResponse(status=200, headers={}, data={"id": "req_capacity", "choices": [{"message": {"content": "OK"}}]})]
    )
    context = ProviderRequestContext(
        tenant_id="tenant_1", project_id="project_1", idempotency_key="task_capacity_1"
    )
    gateway = ProviderGateway(
        env=qianwen_env(), transport=transport, capacity_ledger=capacity
    )

    gateway.generate("qianwen", "测试", request_context=context)

    assert capacity.context == context
    assert capacity.released_lease is not None
    assert capacity.released_lease.released is True


def test_capacity_cleanup_failure_never_replays_successful_provider_call() -> None:
    class FailingCleanupCapacityLedger:
        def acquire_capacity(self, provider, configuration_fingerprint, *, context):
            return ProviderCapacityLease(
                provider=provider,
                configuration_fingerprint=configuration_fingerprint,
                tenant_id=context.tenant_id,
            )

        def release_capacity(self, lease):
            raise RuntimeError("database unavailable during cleanup")

    transport = FakeTransport(
        [HttpResponse(status=200, headers={}, data={"id": "req_once", "choices": [{"message": {"content": "OK"}}]})]
    )
    result = ProviderGateway(
        env=qianwen_env(),
        transport=transport,
        capacity_ledger=FailingCleanupCapacityLedger(),
    ).generate("qianwen", "测试")

    assert result.answer_text == "OK"
    assert len(transport.calls) == 1


def test_quota_reservation_is_released_after_failed_request() -> None:
    ledger = InMemoryQuotaLedger({"qianwen": 1})
    failing_transport = FakeTransport(
        [ProviderGatewayError("qianwen", "PROVIDER_AUTH_FAILED", "unauthorized")]
    )
    gateway = ProviderGateway(
        env=qianwen_env(), transport=failing_transport, quota_ledger=ledger, max_attempts=1
    )
    with pytest.raises(ProviderGatewayError):
        gateway.generate("qianwen", "测试")

    succeeding_transport = FakeTransport(
        [
            HttpResponse(
                status=200,
                headers={},
                data={"id": "req_2", "choices": [{"message": {"content": "OK"}}]},
            )
        ]
    )
    second = ProviderGateway(
        env=qianwen_env(), transport=succeeding_transport, quota_ledger=ledger, max_attempts=1
    )
    assert second.generate("qianwen", "测试").answer_text == "OK"


def test_l1_l2_and_l3_probe_are_distinct() -> None:
    transport = FakeTransport(
        [
            HttpResponse(status=200, headers={}, data={"data": [{"id": "qwen-test"}]}),
            HttpResponse(status=200, headers={}, data={"data": [{"id": "qwen-test"}]}),
            HttpResponse(
                status=200,
                headers={"x-request-id": "request_probe"},
                data={"choices": [{"message": {"content": "OK"}}]},
            ),
        ]
    )
    gateway = ProviderGateway(env=qianwen_env(), transport=transport)

    assert gateway.probe("qianwen", ProbeLevel.NETWORK).state == HealthState.HEALTHY
    assert gateway.probe("qianwen", ProbeLevel.AUTH_MODEL).state == HealthState.HEALTHY
    l3 = gateway.probe("qianwen", ProbeLevel.GENERATION)
    assert l3.state == HealthState.HEALTHY
    assert l3.request_id_present is True
    assert transport.network_probe_count == 3


def test_unconfigured_provider_probe_does_not_make_network_call() -> None:
    transport = FakeTransport([])
    probes = []
    result = ProviderGateway(env={}, transport=transport, probe_sink=probes.append).probe(
        "kimi", ProbeLevel.GENERATION
    )

    assert result.state == HealthState.UNCONFIGURED
    assert transport.network_probe_count == 0
    assert probes == [result]


def test_l2_probe_distinguishes_missing_model_from_auth_success() -> None:
    transport = FakeTransport(
        [HttpResponse(status=200, headers={}, data={"data": [{"id": "another-model"}]})]
    )
    result = ProviderGateway(env=qianwen_env(), transport=transport).probe(
        "qianwen", ProbeLevel.AUTH_MODEL
    )

    assert result.state == HealthState.MODEL_FAILED
    assert result.error_code == "PROVIDER_MODEL_UNAVAILABLE"


def test_expiring_model_is_blocked_by_configurable_migration_window() -> None:
    gateway = ProviderGateway(
        env={
            "DEEPSEEK_API_KEY": "secret",
            "DEEPSEEK_API_URL": "https://deepseek.example.test/v1/chat/completions",
            "DEEPSEEK_MODEL": "deepseek-v3.2",
            "AIRANK_PROVIDER_MODEL_MIN_DAYS_TO_SUNSET": "10000",
            "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "true",
        },
        transport=FakeTransport([]),
    )

    with pytest.raises(ProviderGatewayError) as caught:
        gateway.generate("deepseek", "测试")
    assert caught.value.code in {"PROVIDER_MODEL_MIGRATION_REQUIRED", "PROVIDER_MODEL_EXPIRED"}
