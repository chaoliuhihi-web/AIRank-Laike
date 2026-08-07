from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    ImplementationStatus,
    ModelLifecycle,
    ProviderCapabilities,
    ProviderManifest,
)


PROVIDER_ALIASES = {"tongyi": "qianwen"}


PROVIDER_MANIFESTS: dict[str, ProviderManifest] = {
    "qianwen": ProviderManifest(
        provider="qianwen",
        label="千问",
        implementation_status=ImplementationStatus.PARTIAL,
        collection_mode="provider_api",
        endpoint_env="QIANWEN_API_URL",
        endpoint_default="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        key_env="QIANWEN_API_KEY",
        model_env="QIANWEN_MODEL",
        model_default="qwen-plus",
        disabled_env="QIANWEN_PROVIDER_DISABLED",
        request_kind="chat_completions_search",
        capabilities=ProviderCapabilities(web_search=True, citations=True),
        allowed_endpoint_hosts=("dashscope.aliyuncs.com",),
    ),
    "doubao": ProviderManifest(
        provider="doubao",
        label="豆包",
        implementation_status=ImplementationStatus.PARTIAL,
        collection_mode="provider_api",
        endpoint_env="DOUBAO_API_URL",
        endpoint_default="https://ark.cn-beijing.volces.com/api/v3/responses",
        key_env="DOUBAO_API_KEY",
        model_env="DOUBAO_MODEL",
        model_default="doubao-seed-2-0-lite-260215",
        disabled_env="DOUBAO_PROVIDER_DISABLED",
        request_kind="responses_web_search",
        capabilities=ProviderCapabilities(web_search=True, citations=True),
        allowed_endpoint_hosts=("ark.cn-beijing.volces.com",),
    ),
    "kimi": ProviderManifest(
        provider="kimi",
        label="Kimi",
        implementation_status=ImplementationStatus.PARTIAL,
        collection_mode="provider_api",
        endpoint_env="KIMI_API_URL",
        endpoint_default="https://api.moonshot.cn/v1/chat/completions",
        key_env="KIMI_API_KEY",
        model_env="KIMI_MODEL",
        model_default="kimi-k3",
        disabled_env="KIMI_PROVIDER_DISABLED",
        request_kind="chat_completions",
        capabilities=ProviderCapabilities(web_search=True, citations=True),
        allowed_endpoint_hosts=("api.moonshot.cn",),
    ),
    "deepseek": ProviderManifest(
        provider="deepseek",
        label="DeepSeek",
        implementation_status=ImplementationStatus.PARTIAL,
        collection_mode="provider_api",
        endpoint_env="DEEPSEEK_API_URL",
        endpoint_default="https://api.deepseek.com/v1/chat/completions",
        key_env="DEEPSEEK_API_KEY",
        model_env="DEEPSEEK_MODEL",
        model_default="deepseek-chat",
        disabled_env="DEEPSEEK_PROVIDER_DISABLED",
        request_kind="chat_completions",
        capabilities=ProviderCapabilities(web_search=False, citations=False),
        allowed_endpoint_hosts=("api.deepseek.com", "dashscope.aliyuncs.com"),
        lifecycle={
            "deepseek-v3.2": ModelLifecycle(
                sunset_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
                replacement="deepseek-v4-pro",
                source="provider_announcement",
            )
        },
    ),
}


def canonical_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    return PROVIDER_ALIASES.get(normalized, normalized)


def get_manifest(provider: str) -> ProviderManifest | None:
    return PROVIDER_MANIFESTS.get(canonical_provider(provider))
