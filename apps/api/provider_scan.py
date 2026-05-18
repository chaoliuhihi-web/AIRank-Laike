from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_PROVIDER_LABELS: dict[str, str] = {
    "chatgpt": "ChatGPT",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "tongyi": "通义",
    "doubao": "豆包",
    "baidu_ai_search": "百度 AI 搜索",
    "yuanbao": "腾讯元宝",
}

PROVIDER_WEB_URLS: dict[str, str] = {
    "chatgpt": "https://chatgpt.com/",
    "deepseek": "https://chat.deepseek.com/",
    "kimi": "https://www.kimi.com/",
    "tongyi": "https://www.tongyi.com/qianwen/",
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


@dataclass(frozen=True)
class ProviderScanResult:
    provider: str
    provider_label: str
    answer_text: str
    brand_mentioned: bool
    brand_rank: int | None
    competitor_mentions: list[dict[str, Any]]
    sentiment: str
    confidence: float
    external_trace_id: str | None
    raw_metadata: dict[str, Any]


@dataclass(frozen=True)
class BrowserProviderConfig:
    provider: str
    label: str
    url: str
    profile_dir: Path
    headless: bool
    timeout_seconds: float

    def public_metadata(self) -> dict[str, str | bool | float]:
        return {
            "provider": self.provider,
            "label": self.label,
            "url": self.url,
            "profile_dir": str(self.profile_dir),
            "headless": self.headless,
            "timeout_seconds": self.timeout_seconds,
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
    def __init__(self, provider: str, reason: str, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.provider = provider
        self.reason = reason
        self.status_code = status_code


def provider_execution_mode() -> str:
    mode = os.getenv("AIRANK_PROVIDER_MODE", "browser").strip().lower()
    if mode in {"mock", "generated", "fixture", "dev"}:
        return "mock"
    return "browser"


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
    )


def browser_timeout_seconds() -> float:
    raw_timeout = os.getenv("AIRANK_BROWSER_TIMEOUT_SECONDS", str(DEFAULT_BROWSER_TIMEOUT_SECONDS))
    try:
        return max(15.0, float(raw_timeout))
    except ValueError:
        return DEFAULT_BROWSER_TIMEOUT_SECONDS


def call_provider_for_brand_rank(
    provider: str,
    brand_name: str,
    website_url: str,
    industry: str,
    competitor_names: list[str],
    question_text: str,
) -> ProviderScanResult:
    config = browser_provider_config(provider)
    prompt = build_brand_rank_prompt(brand_name, website_url, industry, competitor_names, question_text)
    try:
        with provider_lock(provider):
            browser_result = run_browser_probe(config, prompt)
    except PlaywrightTimeoutError as exc:
        raise ProviderCallError(provider, f"browser timeout: {str(exc)[:500]}") from exc
    except PlaywrightError as exc:
        raise ProviderCallError(provider, f"browser automation failed: {str(exc)[:500]}") from exc
    except RuntimeError as exc:
        raise ProviderCallError(provider, str(exc)[:1000]) from exc

    parsed = parse_provider_answer(browser_result["answer_text"], brand_name, competitor_names)
    if looks_login_blocked(browser_result["answer_text"]):
        raise ProviderCallError(provider, "web page returned login or human verification text instead of an answer")
    if not answer_mentions_any_brand(browser_result["answer_text"], [brand_name, *competitor_names]):
        raise ProviderCallError(provider, "web page did not return an answer mentioning the requested brand or competitors")
    return ProviderScanResult(
        provider=provider,
        provider_label=config.label,
        answer_text=parsed["answer_text"],
        brand_mentioned=parsed["brand_mentioned"],
        brand_rank=parsed["brand_rank"],
        competitor_mentions=parsed["competitor_mentions"],
        sentiment=parsed["sentiment"],
        confidence=parsed["confidence"],
        external_trace_id=browser_result["trace_id"],
        raw_metadata={
            **config.public_metadata(),
            "capture_url": browser_result["page_url"],
            "capture_title": browser_result["title"],
            "screenshot_path": browser_result["screenshot_path"],
            "answer_parse_mode": parsed["parse_mode"],
            "capture_mode": "consumer_browser",
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
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=config.headless,
            viewport={"width": 1440, "height": 1000},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
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
            screenshot_path = save_page_screenshot(page, config.provider)
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
) -> str:
    competitors = "、".join(competitor_names) if competitor_names else "无指定竞品"
    return (
        f"{question_text}\n\n"
        f"请以企业买家的角度回答。待评估品牌是：{brand_name}（官网：{website_url}），"
        f"行业：{industry}，对标/竞品：{competitors}。"
        "请在回答里给出你认为这些品牌的推荐排序，并说明原因。"
    )


def run_browser_probe(config: BrowserProviderConfig, prompt: str) -> dict[str, str]:
    deadline = time.monotonic() + config.timeout_seconds
    trace_id = f"browser:{config.provider}:{int(time.time())}"
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=config.headless,
            viewport={"width": 1440, "height": 1000},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
        )
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
                screenshot_path = save_page_screenshot(page, config.provider)
                raise RuntimeError(f"{config.label} web page requires login or human verification; screenshot={screenshot_path}")

            input_locator = find_prompt_input(page)
            if input_locator is None:
                screenshot_path = save_page_screenshot(page, config.provider)
                raise RuntimeError(f"{config.label} web page prompt input was not found; screenshot={screenshot_path}")

            input_locator.click()
            fill_prompt(input_locator, prompt)
            submit_prompt(page, input_locator)
            answer_text = wait_for_answer_text(page, before_text, prompt, deadline)
            screenshot_path = save_page_screenshot(page, config.provider)
            return {
                "trace_id": trace_id,
                "page_url": page.url,
                "title": page.title(),
                "answer_text": answer_text,
                "screenshot_path": screenshot_path,
            }
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


def answer_mentions_any_brand(answer_text: str, names: list[str]) -> bool:
    return any(name and name in answer_text for name in names)


def save_page_screenshot(page: Any, provider: str) -> str:
    root = Path(os.getenv("AIRANK_BROWSER_CAPTURE_DIR") or Path(tempfile.gettempdir()) / "airank-browser-captures")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{provider}-{int(time.time())}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except PlaywrightError:
        return ""
    return str(path)


def parse_provider_answer(content: str, brand_name: str, competitor_names: list[str]) -> dict[str, Any]:
    answer_text = content.strip()
    ranking_payload = extract_rank_lines(answer_text, [brand_name, *competitor_names])
    brand_mentioned = brand_name in answer_text
    brand_rank = rank_for_brand(ranking_payload, brand_name)
    if brand_rank is None:
        brand_rank = infer_rank_from_text(answer_text, brand_name, competitor_names)
    competitor_mentions = build_competitor_mentions(answer_text, ranking_payload, competitor_names)
    sentiment = infer_sentiment(answer_text, brand_name)
    return {
        "answer_text": answer_text,
        "brand_mentioned": brand_mentioned,
        "brand_rank": brand_rank,
        "competitor_mentions": competitor_mentions,
        "sentiment": sentiment,
        "confidence": 0.72 if brand_mentioned else 0.58,
        "parse_mode": "browser_text",
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


def infer_rank_from_text(answer_text: str, brand_name: str, competitor_names: list[str]) -> int | None:
    positions = []
    for name in [brand_name, *competitor_names]:
        position = answer_text.find(name)
        if position >= 0:
            positions.append((position, name))
    if not positions:
        return None
    positions.sort(key=lambda item: item[0])
    for index, (_, name) in enumerate(positions, start=1):
        if name == brand_name:
            return index
    return None


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
