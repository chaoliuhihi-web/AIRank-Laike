from __future__ import annotations

from typing import Any, Mapping

import pytest

from airank_provider_gateway import (
    CircuitBreaker,
    HealthState,
    HttpResponse,
    InMemoryQuotaLedger,
    ProbeLevel,
    ProviderGateway,
    ProviderGatewayError,
    UsagePrecision,
    canonical_provider,
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
    assert result.usage.total_tokens == 20
    assert result.usage.precision == UsagePrecision.EXACT
    assert transport.calls[0]["payload"]["enable_search"] is True
    assert "Authorization" not in audits[0]
    assert audits[0]["request_id_present"] is True


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
    result = ProviderGateway(env={}, transport=transport).probe("kimi", ProbeLevel.GENERATION)

    assert result.state == HealthState.UNCONFIGURED
    assert transport.network_probe_count == 0


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
