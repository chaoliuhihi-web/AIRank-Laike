from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from airank_domain.measurement import BrandEntity, MentionClass, PromptCohortType, find_entity_mentions, sha256_text
from airank_provider_gateway import (
    HealthState,
    ProbeLevel,
    ProviderGateway,
    ProviderGatewayError,
    ProviderRequestContext,
)


DEFAULT_PROVIDER_LABELS: dict[str, str] = {
    "chatgpt": "ChatGPT",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "tongyi": "通义",
    "qianwen": "千问",
    "doubao": "豆包",
    "baidu_ai_search": "百度 AI 搜索",
    "yuanbao": "腾讯元宝",
}

PROVIDER_WEB_URLS: dict[str, str] = {
    "chatgpt": "https://chatgpt.com/",
    "deepseek": "https://chat.deepseek.com/",
    "kimi": "https://www.kimi.com/",
    "tongyi": "https://www.tongyi.com/qianwen/",
    "qianwen": "https://www.tongyi.com/qianwen/",
    "doubao": "https://www.doubao.com/chat/",
    "baidu_ai_search": "https://chat.baidu.com/",
    "yuanbao": "https://yuanbao.tencent.com/",
}

LOGIN_BLOCK_PATTERNS = (
    "登录",
    "登陆",
    "注册",
    "sign in",
    "log in",
    "验证码",
    "验证你是真人",
    "verify you are human",
    "captcha",
)

ANSWER_STABLE_SECONDS = 3.0
DEFAULT_BROWSER_TIMEOUT_SECONDS = 90.0
PROVIDER_LOCKS: dict[str, threading.Lock] = {}
PROVIDER_LOCKS_LOCK = threading.Lock()
_API_GATEWAY: ProviderGateway | None = None
_API_PROVIDER_OPERATIONS: Any | None = None


@dataclass(frozen=True)
class ProviderScanResult:
    provider: str
    provider_label: str
    answer_text: str
    brand_mentioned: bool
    brand_rank: int | None
    competitor_mentions: list[dict[str, Any]]
    sentiment: str
    mention_class: str
    target_entity_mentions: list[dict[str, Any]]
    confidence: float | None
    external_trace_id: str | None
    native_citations: list[dict[str, str]]
    raw_metadata: dict[str, Any]


@dataclass(frozen=True)
class BrowserProviderConfig:
    provider: str
    label: str
    url: str
    profile_dir: Path
    headless: bool
    timeout_seconds: float
    channel: str | None
    executable_path: str | None

    def public_metadata(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider,
            "label": self.label,
            "url": self.url,
            "profile_dir": str(self.profile_dir),
            "headless": self.headless,
            "timeout_seconds": self.timeout_seconds,
            "channel": self.channel or "",
            "executable_path": self.executable_path or "",
        }


@dataclass(frozen=True)
class ProviderReadinessResult:
    provider: str
    label: str
    status: str
    url: str
    profile_dir: str
    headless: bool
    blocker_code: str | None = None
    reason: str | None = None
    screenshot_path: str | None = None


class ProviderUnavailable(RuntimeError):
    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(reason)
        self.provider = provider
        self.reason = reason


class ProviderCallError(RuntimeError):
    def __init__(
        self,
        provider: str,
        reason: str,
        status_code: int | None = None,
        *,
        error_code: str | None = None,
        provider_code: str | None = None,
        retryable: bool = False,
        public_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.provider = provider
        self.reason = reason
        self.status_code = status_code
        self.error_code = error_code
        self.provider_code = provider_code
        self.retryable = retryable
        self.public_metadata = dict(public_metadata or {})


class BrowserProbeError(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        screenshot_path: str,
        screenshot_sha256: str,
        page_url: str,
        page_title: str,
        trace_id: str,
    ) -> None:
        super().__init__(reason)
        self.reason = re.sub(r";?\s*screenshot=.*$", "", reason).strip()
        self.screenshot_path = screenshot_path
        self.screenshot_sha256 = screenshot_sha256
        self.page_url = page_url
        self.page_title = page_title
        self.trace_id = trace_id


def classify_provider_call_failure(error: ProviderCallError) -> tuple[str, bool]:
    """Keep operational failures separate from action-blocked collection slots."""

    reason = error.reason.lower()
    if "timeout" in reason:
        return "SCAN_PROVIDER_TIMEOUT", False

    provider_code = str(error.error_code or "").upper()
    if provider_code in {
        "PROVIDER_AUTH_FAILED",
        "PROVIDER_MODEL_OR_ENDPOINT_NOT_FOUND",
        "PROVIDER_RATE_OR_QUOTA_LIMITED",
        "PROVIDER_QUOTA_EXHAUSTED",
    }:
        return "SCAN_PROVIDER_BLOCKED", True

    if error.public_metadata.get("capture_mode") == "consumer_browser":
        blocker = classify_blocker_reason(error.reason)
        if blocker in {"login_required", "captcha_required", "prompt_input_missing"}:
            return "SCAN_PROVIDER_BLOCKED", True

    return "SCAN_PROVIDER_FAILED", False


def provider_execution_mode() -> str:
    mode = os.getenv("AIRANK_PROVIDER_MODE", "browser").strip().lower()
    if mode in {"mock", "generated", "fixture", "dev"}:
        return "mock"
    if mode in {"api", "provider_api"}:
        return "api"
    return "browser"


def get_api_gateway() -> ProviderGateway:
    global _API_GATEWAY, _API_PROVIDER_OPERATIONS
    if _API_GATEWAY is None:
        try:
            max_attempts = int(os.getenv("AIRANK_PROVIDER_MAX_ATTEMPTS", "3"))
        except ValueError:
            max_attempts = 3
        try:
            timeout_seconds = float(os.getenv("AIRANK_PROVIDER_TIMEOUT_SECONDS", "90"))
        except ValueError:
            timeout_seconds = 90.0
        database_url = os.getenv("AIRANK_DATABASE_URL")
        if database_url:
            try:
                from .provider_operations import MySQLProviderOperations
            except ImportError:  # pragma: no cover - supports `cd apps/api && uvicorn main:app`.
                from provider_operations import MySQLProviderOperations  # type: ignore[no-redef]

            _API_PROVIDER_OPERATIONS = MySQLProviderOperations(database_url)
            _API_GATEWAY = ProviderGateway(
                max_attempts=max_attempts,
                timeout_seconds=timeout_seconds,
                circuit_breaker=_API_PROVIDER_OPERATIONS,
                quota_ledger=_API_PROVIDER_OPERATIONS,
                probe_sink=_API_PROVIDER_OPERATIONS.record_probe,
            )
            _API_PROVIDER_OPERATIONS.sync_manifests(_API_GATEWAY.manifests())
        else:
            _API_GATEWAY = ProviderGateway(max_attempts=max_attempts, timeout_seconds=timeout_seconds)
    return _API_GATEWAY


def call_api_provider_for_brand_rank(
    provider: str,
    brand_name: str,
    website_url: str,
    industry: str,
    competitor_names: list[str],
    question_text: str,
    cohort_type: PromptCohortType | str = PromptCohortType.BLIND,
    session_id: str | None = None,
    prompt_version_id: str | None = None,
    brand_aliases: list[str] | None = None,
    company_names: list[str] | None = None,
    product_names: list[str] | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
) -> ProviderScanResult:
    normalized_cohort = PromptCohortType(cohort_type)
    isolated_session_id = session_id or f"session_{uuid4().hex}"
    prompt = build_brand_rank_prompt(
        brand_name,
        website_url,
        industry,
        competitor_names,
        question_text,
        cohort_type=normalized_cohort,
        brand_aliases=brand_aliases,
        company_names=company_names,
        product_names=product_names,
    )
    gateway = get_api_gateway()
    try:
        api_result = gateway.generate(
            provider,
            prompt,
            request_context=ProviderRequestContext(
                tenant_id=tenant_id or "__system__",
                project_id=project_id or "",
                idempotency_key=(
                    f"scan:{tenant_id}:{project_id}:{task_id}"
                    if tenant_id and project_id and task_id
                    else f"direct:{isolated_session_id}:{sha256_text(prompt)}"
                ),
            ),
        )
    except ProviderGatewayError as exc:
        if exc.code in {
            "PROVIDER_NOT_CONFIGURED",
            "PROVIDER_DISABLED",
            "PROVIDER_MODEL_EXPIRED",
            "PROVIDER_MODEL_MIGRATION_REQUIRED",
        }:
            raise ProviderUnavailable(provider, exc.message) from exc
        settings = gateway.settings(provider)
        raise ProviderCallError(
            provider,
            exc.message,
            exc.status_code,
            error_code=exc.code,
            provider_code=exc.provider_code,
            retryable=exc.retryable,
            public_metadata={
                "prompt_sha256": sha256_text(prompt),
                "model_name": settings.model,
                "endpoint_host": settings.endpoint_host,
                "configuration_fingerprint": settings.configuration_fingerprint(provider),
                "capture_mode": "provider_api",
            },
        ) from exc

    parsed = parse_provider_answer(
        api_result.answer_text,
        brand_name,
        competitor_names,
        brand_aliases=brand_aliases,
        company_names=company_names,
        product_names=product_names,
    )
    native_citations = [
        {
            "url": citation.url,
            "title": citation.title or "",
            "host": urlparse(citation.url).netloc.lower(),
            "cited_text": citation.cited_text or "",
        }
        for citation in api_result.citations
    ]
    return ProviderScanResult(
        provider=api_result.provider,
        provider_label=DEFAULT_PROVIDER_LABELS.get(api_result.provider, api_result.provider),
        answer_text=parsed["answer_text"],
        brand_mentioned=parsed["brand_mentioned"],
        brand_rank=parsed["brand_rank"],
        competitor_mentions=parsed["competitor_mentions"],
        sentiment=parsed["sentiment"],
        mention_class=parsed["mention_class"],
        target_entity_mentions=parsed["target_entity_mentions"],
        confidence=parsed["confidence"],
        external_trace_id=api_result.request_id,
        native_citations=native_citations,
        raw_metadata={
            "capture_mode": "provider_api",
            "collector_surface": "api",
            "evidence_level": api_result.evidence_grade,
            "cohort_type": normalized_cohort.value,
            "session_id": isolated_session_id,
            "prompt_version_id": prompt_version_id,
            "prompt_sha256": sha256_text(prompt),
            "answer_sha256": sha256_text(parsed["answer_text"]),
            "answer_parse_mode": parsed["parse_mode"],
            "model_name": api_result.model,
            "search_requested": api_result.web_search_requested,
            "search_used": api_result.web_search_used,
            "provider_request_id": api_result.request_id,
            "requested_at": api_result.requested_at.isoformat(),
            "completed_at": api_result.completed_at.isoformat(),
            "duration_ms": api_result.duration_ms,
            "attempt_count": api_result.attempt_count,
            "usage": {
                "input_tokens": api_result.usage.input_tokens,
                "output_tokens": api_result.usage.output_tokens,
                "total_tokens": api_result.usage.total_tokens,
                "precision": api_result.usage.precision.value,
                "source": api_result.usage.source,
            },
            "endpoint_host": api_result.endpoint_host,
            "configuration_fingerprint": api_result.configuration_fingerprint,
            "source_extraction": "provider_native_payload",
            "provider_raw_response": api_result.raw_response,
        },
    )


def probe_api_provider_readiness(provider: str) -> ProviderReadinessResult:
    gateway = get_api_gateway()
    settings = gateway.settings(provider)
    result = gateway.probe(provider, ProbeLevel.GENERATION)
    ready = result.state == HealthState.HEALTHY
    blocker_code_by_state = {
        HealthState.UNCONFIGURED: "provider_not_configured",
        HealthState.DISABLED: "provider_disabled",
        HealthState.NETWORK_FAILED: "network_error",
        HealthState.AUTH_FAILED: "provider_auth_failed",
        HealthState.MODEL_FAILED: "provider_model_failed",
        HealthState.GENERATION_FAILED: "provider_generation_failed",
        HealthState.CIRCUIT_OPEN: "provider_circuit_open",
    }
    return ProviderReadinessResult(
        provider=result.provider,
        label=DEFAULT_PROVIDER_LABELS.get(result.provider, result.provider),
        status="ready" if ready else "blocked",
        url=f"https://{settings.endpoint_host}" if settings.endpoint_host else "",
        profile_dir="",
        headless=True,
        blocker_code=None if ready else blocker_code_by_state.get(result.state, "unknown_blocked"),
        reason=result.message,
    )


def browser_provider_config(provider: str) -> BrowserProviderConfig:
    if provider not in PROVIDER_WEB_URLS:
        raise ProviderUnavailable(provider, f"{provider} web provider is not configured")
    provider_key = provider.upper()
    profile_root = os.getenv("AIRANK_BROWSER_PROFILE_DIR") or str(Path(".runtime") / "browser-profiles")
    profile_dir = Path(profile_root).expanduser().resolve() / provider
    profile_dir.mkdir(parents=True, exist_ok=True)
    return BrowserProviderConfig(
        provider=provider,
        label=DEFAULT_PROVIDER_LABELS.get(provider, provider),
        url=os.getenv(f"AIRANK_{provider_key}_WEB_URL", PROVIDER_WEB_URLS[provider]).strip(),
        profile_dir=profile_dir,
        headless=os.getenv("AIRANK_BROWSER_HEADLESS", "1").strip().lower() not in {"0", "false", "no"},
        timeout_seconds=browser_timeout_seconds(),
        channel=empty_env_to_none(os.getenv("AIRANK_BROWSER_CHANNEL")),
        executable_path=empty_env_to_none(os.getenv("AIRANK_BROWSER_EXECUTABLE_PATH")),
    )


def browser_timeout_seconds() -> float:
    raw_timeout = os.getenv("AIRANK_BROWSER_TIMEOUT_SECONDS", str(DEFAULT_BROWSER_TIMEOUT_SECONDS))
    try:
        return max(15.0, float(raw_timeout))
    except ValueError:
        return DEFAULT_BROWSER_TIMEOUT_SECONDS


def empty_env_to_none(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def launch_provider_context(playwright: Any, config: BrowserProviderConfig, *, headless: bool | None = None) -> Any:
    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(config.profile_dir),
        "headless": config.headless if headless is None else headless,
        "viewport": {"width": 1440, "height": 1000},
        "locale": "zh-CN",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if config.channel:
        launch_kwargs["channel"] = config.channel
    if config.executable_path:
        launch_kwargs["executable_path"] = config.executable_path
    return playwright.chromium.launch_persistent_context(**launch_kwargs)


def call_provider_for_brand_rank(
    provider: str,
    brand_name: str,
    website_url: str,
    industry: str,
    competitor_names: list[str],
    question_text: str,
    cohort_type: PromptCohortType | str = PromptCohortType.BLIND,
    session_id: str | None = None,
    prompt_version_id: str | None = None,
    brand_aliases: list[str] | None = None,
    company_names: list[str] | None = None,
    product_names: list[str] | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    task_id: str | None = None,
) -> ProviderScanResult:
    del tenant_id, project_id, task_id  # shared task contract; browser evidence has its own session scope.
    config = browser_provider_config(provider)
    normalized_cohort = PromptCohortType(cohort_type)
    isolated_session_id = session_id or f"session_{uuid4().hex}"
    prompt = build_brand_rank_prompt(
        brand_name,
        website_url,
        industry,
        competitor_names,
        question_text,
        cohort_type=normalized_cohort,
        brand_aliases=brand_aliases,
        company_names=company_names,
        product_names=product_names,
    )
    try:
        with provider_lock(provider):
            browser_result = run_browser_probe(config, prompt)
    except BrowserProbeError as exc:
        raise ProviderCallError(
            provider,
            exc.reason[:1000],
            public_metadata={
                **config.public_metadata(),
                "capture_mode": "consumer_browser",
                "collector_surface": "web",
                "evidence_level": "consumer_web",
                "session_id": isolated_session_id,
                "prompt_version_id": prompt_version_id,
                "prompt_sha256": sha256_text(prompt),
                "capture_url": exc.page_url,
                "capture_title": exc.page_title,
                "browser_trace_id": exc.trace_id,
                "screenshot_path": exc.screenshot_path,
                "screenshot_sha256": exc.screenshot_sha256,
                "source_panel_status": "not_inspected",
            },
        ) from exc
    except PlaywrightTimeoutError as exc:
        raise ProviderCallError(provider, f"browser timeout: {str(exc)[:500]}") from exc
    except PlaywrightError as exc:
        raise ProviderCallError(provider, f"browser automation failed: {str(exc)[:500]}") from exc
    except RuntimeError as exc:
        raise ProviderCallError(provider, str(exc)[:1000]) from exc

    parsed = parse_provider_answer(
        browser_result["answer_text"],
        brand_name,
        competitor_names,
        brand_aliases=brand_aliases,
        company_names=company_names,
        product_names=product_names,
    )
    if looks_login_blocked(browser_result["answer_text"]):
        raise ProviderCallError(provider, "web page returned login or human verification text instead of an answer")
    return ProviderScanResult(
        provider=provider,
        provider_label=config.label,
        answer_text=parsed["answer_text"],
        brand_mentioned=parsed["brand_mentioned"],
        brand_rank=parsed["brand_rank"],
        competitor_mentions=parsed["competitor_mentions"],
        sentiment=parsed["sentiment"],
        mention_class=parsed["mention_class"],
        target_entity_mentions=parsed["target_entity_mentions"],
        confidence=parsed["confidence"],
        external_trace_id=browser_result["trace_id"],
        native_citations=browser_result.get("source_links", []),
        raw_metadata={
            **config.public_metadata(),
            "capture_url": browser_result["page_url"],
            "capture_title": browser_result["title"],
            "screenshot_path": browser_result["screenshot_path"],
            "screenshot_sha256": browser_result.get("screenshot_sha256", ""),
            "source_panel_status": browser_result.get("source_panel_status", "not_inspected"),
            "source_panel_screenshot_path": browser_result.get("source_panel_screenshot_path", ""),
            "source_panel_screenshot_sha256": browser_result.get("source_panel_screenshot_sha256", ""),
            "source_panel_capture_mode": browser_result.get("source_panel_capture_mode", "not_inspected"),
            "answer_parse_mode": parsed["parse_mode"],
            "capture_mode": "consumer_browser",
            "collector_surface": "web",
            "evidence_level": "consumer_web",
            "cohort_type": normalized_cohort.value,
            "session_id": isolated_session_id,
            "prompt_version_id": prompt_version_id,
            "prompt_sha256": sha256_text(prompt),
            "answer_sha256": sha256_text(parsed["answer_text"]),
            "source_extraction": "visible_anchor_text_match",
        },
    )


def provider_lock(provider: str) -> threading.Lock:
    with PROVIDER_LOCKS_LOCK:
        lock = PROVIDER_LOCKS.get(provider)
        if lock is None:
            lock = threading.Lock()
            PROVIDER_LOCKS[provider] = lock
        return lock


def probe_provider_readiness(provider: str) -> ProviderReadinessResult:
    if provider_execution_mode() == "api":
        return probe_api_provider_readiness(provider)
    config = browser_provider_config(provider)
    try:
        with provider_lock(provider):
            return run_browser_readiness_probe(config)
    except ProviderUnavailable:
        raise
    except PlaywrightTimeoutError as exc:
        return ProviderReadinessResult(
            provider=provider,
            label=config.label,
            status="blocked",
            url=config.url,
            profile_dir=str(config.profile_dir),
            headless=config.headless,
            blocker_code="timeout",
            reason=f"browser timeout: {str(exc)[:300]}",
        )
    except PlaywrightError as exc:
        return ProviderReadinessResult(
            provider=provider,
            label=config.label,
            status="blocked",
            url=config.url,
            profile_dir=str(config.profile_dir),
            headless=config.headless,
            blocker_code="network_error",
            reason=f"browser automation failed: {str(exc)[:300]}",
        )
    except RuntimeError as exc:
        return ProviderReadinessResult(
            provider=provider,
            label=config.label,
            status="blocked",
            url=config.url,
            profile_dir=str(config.profile_dir),
            headless=config.headless,
            blocker_code=classify_blocker_reason(str(exc)),
            reason=str(exc)[:300],
        )


def run_browser_readiness_probe(config: BrowserProviderConfig) -> ProviderReadinessResult:
    with sync_playwright() as playwright:
        context = launch_provider_context(playwright, config)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(int(config.timeout_seconds * 1000))
        try:
            try:
                page.goto(config.url, wait_until="domcontentloaded", timeout=int(config.timeout_seconds * 1000))
                page.wait_for_load_state("networkidle", timeout=min(10000, int(config.timeout_seconds * 1000)))
            except PlaywrightTimeoutError:
                pass

            body_text = normalized_body_text(page)
            prompt_input_found = find_prompt_input(page) is not None
            screenshot_path, _ = save_page_screenshot(page, config.provider)
            page_url = page.url
        finally:
            context.close()

    if looks_login_blocked(body_text):
        return ProviderReadinessResult(
            provider=config.provider,
            label=config.label,
            status="blocked",
            url=page_url,
            profile_dir=str(config.profile_dir),
            headless=config.headless,
            blocker_code=classify_login_blocker(body_text),
            reason="login or human verification is visible",
            screenshot_path=screenshot_path,
        )
    if not prompt_input_found:
        return ProviderReadinessResult(
            provider=config.provider,
            label=config.label,
            status="blocked",
            url=page_url,
            profile_dir=str(config.profile_dir),
            headless=config.headless,
            blocker_code="prompt_input_missing",
            reason="prompt input was not found",
            screenshot_path=screenshot_path,
        )
    return ProviderReadinessResult(
        provider=config.provider,
        label=config.label,
        status="ready",
        url=page_url,
        profile_dir=str(config.profile_dir),
        headless=config.headless,
        blocker_code=None,
        screenshot_path=screenshot_path,
    )


def build_brand_rank_prompt(
    brand_name: str,
    website_url: str,
    industry: str,
    competitor_names: list[str],
    question_text: str,
    *,
    cohort_type: PromptCohortType | str = PromptCohortType.BLIND,
    brand_aliases: list[str] | None = None,
    company_names: list[str] | None = None,
    product_names: list[str] | None = None,
) -> str:
    cohort = PromptCohortType(cohort_type)
    question = question_text.strip()
    if cohort == PromptCohortType.BLIND:
        protected_names = [brand_name, *(brand_aliases or ()), *(company_names or ()), *(product_names or ())]
        leaked = [name for name in protected_names if name and name.casefold() in question.casefold()]
        if leaked:
            raise ValueError("blind cohort question must not include target brand, company, alias, or product names")
        return question
    if cohort == PromptCohortType.FACT_VERIFICATION:
        return (
            f"请核验以下关于 {brand_name}（官网：{website_url}）的问题，只陈述可由来源支持的事实，"
            f"逐条给出来源链接；无法确认时明确回答无法确认：\n{question}"
        )
    if cohort == PromptCohortType.ASSISTED:
        return (
            f"{question}\n\n待评估品牌是 {brand_name}（官网：{website_url}），行业：{industry}。"
            "请说明它是否适合作为候选，并区分事实、判断与无法确认的信息。"
        )
    competitors = "、".join(competitor_names) if competitor_names else "无指定竞品"
    return (
        f"{question}\n\n"
        f"请以企业买家的角度回答。待评估品牌是：{brand_name}（官网：{website_url}），"
        f"行业：{industry}，对标/竞品：{competitors}。"
        "请在回答里给出你认为这些品牌的推荐排序，并说明原因。"
    )


def run_browser_probe(config: BrowserProviderConfig, prompt: str) -> dict[str, Any]:
    deadline = time.monotonic() + config.timeout_seconds
    trace_id = f"browser:{config.provider}:{int(time.time())}"
    with sync_playwright() as playwright:
        context = launch_provider_context(playwright, config)
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(int(config.timeout_seconds * 1000))
        try:
            try:
                page.goto(config.url, wait_until="domcontentloaded", timeout=int(config.timeout_seconds * 1000))
                page.wait_for_load_state("networkidle", timeout=min(15000, int(config.timeout_seconds * 1000)))
            except PlaywrightTimeoutError:
                pass

            before_text = normalized_body_text(page)
            if looks_login_blocked(before_text) and not find_prompt_input(page):
                raise RuntimeError(f"{config.label} web page requires login or human verification")

            input_locator = find_prompt_input(page)
            if input_locator is None:
                raise RuntimeError(f"{config.label} web page prompt input was not found")

            input_locator.click()
            fill_prompt(input_locator, prompt)
            submit_prompt(page, input_locator)
            answer_text = wait_for_answer_text(page, before_text, prompt, deadline)
            screenshot_path, screenshot_sha256 = save_page_screenshot(page, config.provider)
            source_links = extract_visible_source_links(page, answer_text)
            source_panel_status = "captured" if source_links else "not_present"
            return {
                "trace_id": trace_id,
                "page_url": page.url,
                "title": page.title(),
                "answer_text": answer_text,
                "screenshot_path": screenshot_path,
                "screenshot_sha256": screenshot_sha256,
                "source_links": source_links,
                "source_panel_status": source_panel_status,
                # The full-page capture is valid source-panel evidence only when
                # every accepted source link was visible in the captured answer.
                "source_panel_screenshot_path": screenshot_path if source_links else "",
                "source_panel_screenshot_sha256": screenshot_sha256 if source_links else "",
                "source_panel_capture_mode": (
                    "whole_page_visible_source_links" if source_links else "visible_page_inspected_no_sources"
                ),
            }
        except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
            screenshot_path, screenshot_sha256 = save_page_screenshot(page, config.provider)
            try:
                page_url = page.url
                page_title = page.title()
            except PlaywrightError:
                page_url = config.url
                page_title = ""
            raise BrowserProbeError(
                str(exc) or exc.__class__.__name__,
                screenshot_path=screenshot_path,
                screenshot_sha256=screenshot_sha256,
                page_url=page_url,
                page_title=page_title,
                trace_id=trace_id,
            ) from exc
        finally:
            context.close()


def find_prompt_input(page: Any) -> Any | None:
    selectors = [
        "textarea:not([disabled])",
        "[contenteditable='true']",
        "div[role='textbox']",
        "input[type='text']:not([disabled])",
        "input:not([type]):not([disabled])",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        count = min(locator.count(), 8)
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible() and candidate.is_enabled() and not is_login_input(candidate):
                    box = candidate.bounding_box()
                    if box and box["width"] >= 80 and box["height"] >= 18:
                        return candidate
            except PlaywrightError:
                continue
    return None


def is_login_input(locator: Any) -> bool:
    attrs = []
    for attr_name in ("type", "placeholder", "aria-label", "name", "autocomplete"):
        try:
            attr_value = locator.get_attribute(attr_name, timeout=500)
        except PlaywrightError:
            attr_value = None
        if attr_value:
            attrs.append(str(attr_value).lower())
    joined = " ".join(attrs)
    login_markers = (
        "phone",
        "mobile",
        "手机号",
        "手机",
        "验证码",
        "verification code",
        "sms code",
        "captcha",
        "login",
        "登录",
        "password",
        "密码",
        "email",
        "邮箱",
        "account",
        "账号",
        "username",
    )
    return any(marker in joined for marker in login_markers)


def fill_prompt(input_locator: Any, prompt: str) -> None:
    try:
        input_locator.fill(prompt)
        return
    except PlaywrightError:
        pass
    input_locator.click()
    input_locator.press("Meta+A")
    input_locator.press("Backspace")
    input_locator.type(prompt, delay=8)


def submit_prompt(page: Any, input_locator: Any) -> None:
    button_selectors = [
        "button[aria-label*='发送']",
        "button[aria-label*='Send']",
        "button:has-text('发送')",
        "button:has-text('Send')",
    ]
    for selector in button_selectors:
        locator = page.locator(selector)
        count = min(locator.count(), 5)
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    candidate.click()
                    return
            except PlaywrightError:
                continue
    input_locator.press("Enter")


def wait_for_answer_text(page: Any, before_text: str, prompt: str, deadline: float) -> str:
    best_text = ""
    last_changed_at = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(1.0)
        current_text = normalized_body_text(page)
        delta = strip_prompt_echo(extract_answer_delta(before_text, current_text), prompt)
        if len(delta) > len(best_text):
            best_text = delta
            last_changed_at = time.monotonic()
        if looks_login_blocked(current_text) and len(best_text) < 40:
            raise RuntimeError("web page requires login or human verification")
        if best_text and looks_login_blocked(best_text):
            raise RuntimeError("web page returned login or human verification text instead of an answer")
        if len(best_text) >= 80 and time.monotonic() - last_changed_at >= ANSWER_STABLE_SECONDS:
            return best_text
    if best_text:
        return best_text
    raise RuntimeError("web answer did not appear before timeout")


def normalized_body_text(page: Any) -> str:
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except PlaywrightError:
        return ""
    return normalize_text(text)


def normalize_text(value: str) -> str:
    lines = [line.strip() for line in value.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def extract_answer_delta(before_text: str, after_text: str) -> str:
    if not after_text:
        return ""
    if before_text and before_text in after_text:
        delta = after_text.split(before_text, 1)[-1]
    else:
        before_lines = set(before_text.splitlines())
        delta_lines = [line for line in after_text.splitlines() if line not in before_lines]
        delta = "\n".join(delta_lines)
    return trim_control_text(delta)


def strip_prompt_echo(text: str, prompt: str) -> str:
    if not text:
        return ""
    if prompt in text:
        text = text.split(prompt)[-1]

    marker = "请在回答里给出你认为这些品牌的推荐排序，并说明原因。"
    if marker in text:
        text = text.split(marker)[-1]

    prompt_compact = compact_text(prompt)
    kept_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        compact_line = compact_text(stripped)
        if compact_line and compact_line in prompt_compact:
            continue
        if prompt_compact and prompt_compact in compact_line:
            continue
        kept_lines.append(stripped)
    return trim_control_text("\n".join(kept_lines))


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def trim_control_text(text: str) -> str:
    blocked_prefixes = (
        "发送",
        "重新生成",
        "复制",
        "点赞",
        "点踩",
        "分享",
        "停止",
        "登录",
        "注册",
    )
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped in blocked_prefixes:
            continue
        if any(stripped.startswith(prefix) and len(stripped) <= 12 for prefix in blocked_prefixes):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def looks_login_blocked(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in LOGIN_BLOCK_PATTERNS)


def classify_login_blocker(text: str) -> str:
    lowered = text.lower()
    captcha_markers = ("验证码", "验证你是真人", "verify you are human", "captcha")
    if any(marker in lowered for marker in captcha_markers):
        return "captcha_required"
    return "login_required"


def classify_blocker_reason(reason: str) -> str:
    lowered = reason.lower()
    if "timeout" in lowered:
        return "timeout"
    if "prompt input" in lowered:
        return "prompt_input_missing"
    if any(marker in lowered for marker in ("login", "sign_in", "sign in", "human verification", "captcha", "验证码")):
        if any(marker in lowered for marker in ("human verification", "captcha", "验证码")):
            return "captcha_required"
        return "login_required"
    if any(marker in lowered for marker in ("net::", "network", "browser automation")):
        return "network_error"
    return "unknown_blocked"


def save_page_screenshot(page: Any, provider: str) -> tuple[str, str]:
    root = Path(os.getenv("AIRANK_BROWSER_CAPTURE_DIR") or Path(tempfile.gettempdir()) / "airank-browser-captures")
    root.mkdir(parents=True, exist_ok=True)
    try:
        payload = page.screenshot(full_page=True)
    except PlaywrightError:
        return "", ""
    digest = hashlib.sha256(payload).hexdigest()
    path = root / provider / digest[:2] / f"{digest}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(payload)
    return str(path), digest


def extract_visible_source_links(page: Any, answer_text: str) -> list[dict[str, str]]:
    """Extract only visible external anchors whose label occurs in the captured answer.

    This deliberately returns an empty list when provenance cannot be tied to the
    answer. Navigation links and the provider's own host are not citations.
    """

    provider_host = urlparse(page.url).netloc.lower()
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        anchors = page.locator("a[href^='http']")
        count = min(anchors.count(), 200)
    except PlaywrightError:
        return []
    for index in range(count):
        anchor = anchors.nth(index)
        try:
            if not anchor.is_visible():
                continue
            url = (anchor.get_attribute("href", timeout=500) or "").strip()
            title = (anchor.inner_text(timeout=500) or "").strip()
        except PlaywrightError:
            continue
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host or host == provider_host or url in seen:
            continue
        if len(title) < 2 or title not in answer_text:
            continue
        seen.add(url)
        citations.append({"url": url, "title": title[:512], "host": host})
    return citations


def parse_provider_answer(
    content: str,
    brand_name: str,
    competitor_names: list[str],
    *,
    brand_aliases: list[str] | None = None,
    company_names: list[str] | None = None,
    product_names: list[str] | None = None,
) -> dict[str, Any]:
    answer_text = content.strip()
    target_entity = BrandEntity(
        canonical_name=brand_name,
        aliases=tuple(brand_aliases or ()),
        company_names=tuple(company_names or ()),
        product_names=tuple(product_names or ()),
    )
    target_mentions = find_entity_mentions(answer_text, target_entity)
    target_names = [name for name, _entity_type in target_entity.names_by_type()]
    ranking_payload = extract_rank_lines(answer_text, [*target_names, *competitor_names])
    brand_mentioned = bool(target_mentions)
    brand_ranks = [rank_for_brand(ranking_payload, name) for name in target_names]
    brand_rank = min((rank for rank in brand_ranks if rank is not None), default=None)
    competitor_mentions = build_competitor_mentions(answer_text, ranking_payload, competitor_names)
    matched_target_name = target_mentions[0].matched_name if target_mentions else brand_name
    sentiment = infer_sentiment(answer_text, matched_target_name)
    mention_class = classify_mention(answer_text, matched_target_name, brand_mentioned, brand_rank, sentiment)
    return {
        "answer_text": answer_text,
        "brand_mentioned": brand_mentioned,
        "brand_rank": brand_rank,
        "competitor_mentions": competitor_mentions,
        "sentiment": sentiment,
        "mention_class": mention_class.value,
        "target_entity_mentions": [
            {
                "canonical_name": mention.canonical_name,
                "matched_name": mention.matched_name,
                "entity_type": mention.entity_type,
                "start": mention.start,
                "end": mention.end,
            }
            for mention in target_mentions
        ],
        "confidence": None,
        "parse_mode": "explicit_rank_and_lexical_classification",
    }


def extract_rank_lines(answer_text: str, brand_names: list[str]) -> list[dict[str, Any]]:
    ranks: list[dict[str, Any]] = []
    for name in brand_names:
        rank = None
        patterns = [
            rf"(第\s*([1-9][0-9]*)\s*[名位][^\n]{{0,40}}{re.escape(name)})",
            rf"({re.escape(name)}[^\n]{{0,40}}第\s*([1-9][0-9]*)\s*[名位])",
            rf"(^|\n)\s*([1-9][0-9]*)[\\.、)]\s*{re.escape(name)}",
        ]
        for pattern in patterns:
            match = re.search(pattern, answer_text)
            if not match:
                continue
            numbers = [group for group in match.groups() if isinstance(group, str) and group.isdigit()]
            if numbers:
                rank = int(numbers[-1])
                break
        if rank is not None:
            ranks.append({"name": name, "rank": rank, "mentioned": name in answer_text})
    return ranks


def rank_for_brand(ranking_payload: list[Any], brand_name: str) -> int | None:
    for item in ranking_payload:
        if not isinstance(item, dict) or item.get("name") != brand_name:
            continue
        rank = item.get("rank")
        if isinstance(rank, int) and rank >= 1:
            return rank
    return None


def classify_mention(
    answer_text: str,
    brand_name: str,
    brand_mentioned: bool,
    brand_rank: int | None,
    sentiment: str,
) -> MentionClass:
    if not brand_mentioned:
        return MentionClass.NOT_MENTIONED
    if sentiment == "negative":
        return MentionClass.NEGATIVE
    first_position = answer_text.find(brand_name)
    window = answer_text[max(0, first_position - 100) : first_position + len(brand_name) + 180]
    recommendation_markers = ("推荐", "首选", "优先考虑", "值得选择", "建议选择")
    candidate_markers = ("候选", "可以考虑", "可选", "备选", "适合")
    if brand_rank is not None or any(marker in window for marker in recommendation_markers):
        return MentionClass.RECOMMENDED
    if any(marker in window for marker in candidate_markers):
        return MentionClass.CANDIDATE
    return MentionClass.MENTIONED


def build_competitor_mentions(answer_text: str, ranking_payload: list[Any], competitor_names: list[str]) -> list[dict[str, Any]]:
    mentions = []
    for competitor_name in competitor_names:
        rank = rank_for_brand(ranking_payload, competitor_name)
        mentioned = competitor_name in answer_text or rank is not None
        mentions.append({"name": competitor_name, "mentioned": mentioned, "rank": rank})
    return mentions


def infer_sentiment(answer_text: str, brand_name: str) -> str:
    if brand_name not in answer_text:
        return "neutral"
    negative_markers = ("不建议", "不推荐", "不足", "风险", "劣势", "谨慎")
    positive_markers = ("推荐", "值得", "优势", "适合", "优先", "领先")
    window_start = max(0, answer_text.find(brand_name) - 120)
    window_end = min(len(answer_text), answer_text.find(brand_name) + 240)
    window = answer_text[window_start:window_end]
    if any(marker in window for marker in negative_markers):
        return "negative"
    if any(marker in window for marker in positive_markers):
        return "positive"
    return "neutral"
