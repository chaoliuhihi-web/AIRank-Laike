from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping
from urllib.parse import urlparse

from .models import ProviderCitation, ProviderManifest, ProviderUsage, UsagePrecision


NATIVE_CITATION_PARSER_VERSION = "airank.provider-native-citation.v2"
SEARCH_EVIDENCE_VERSION = "airank.provider-search-evidence.v1"


def build_request(
    manifest: ProviderManifest,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float | None,
    reasoning_effort: str | None,
    *,
    include_web_search: bool = True,
    request_kind: str | None = None,
) -> dict[str, Any]:
    effective_request_kind = request_kind or manifest.request_kind
    if effective_request_kind == "responses_web_search":
        request: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "max_output_tokens": max_tokens,
        }
        if temperature is not None:
            request["temperature"] = temperature
        if include_web_search:
            request["tools"] = [{"type": "web_search"}]
        return request
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        manifest.max_tokens_field: max_tokens,
    }
    if temperature is not None:
        request["temperature"] = temperature
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort
    if effective_request_kind == "chat_completions_search":
        request.update(
            {
                "enable_search": True,
                "search_options": {"forced_search": True, "search_strategy": "max"},
            }
        )
    return request


def _response_text(data: Mapping[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
            return "\n".join(part for part in parts if part).strip()

    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()
    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "\n".join(parts).strip()
    return ""


def request_uses_web_search(
    request_kind: str,
    payload: Mapping[str, Any],
) -> bool:
    if request_kind == "chat_completions_search":
        return payload.get("enable_search") is True
    if request_kind != "responses_web_search":
        return False
    tools = payload.get("tools")
    return bool(
        isinstance(tools, list)
        and any(
            isinstance(tool, dict) and tool.get("type") == "web_search"
            for tool in tools
        )
    )


def _citation_text(value: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def extract_citations(data: Mapping[str, Any]) -> tuple[ProviderCitation, ...]:
    """Extract only documented/native Provider citation containers.

    Arbitrary URLs in answer text, debug payloads or loosely named nested objects
    are intentionally ignored. This keeps selection evidence distinct from a URL
    that merely happened to occur somewhere in the response JSON.
    """

    candidates: list[ProviderCitation] = []
    seen: set[str] = set()

    def add(value: Any, *, path: str, native_type: str) -> None:
        if not isinstance(value, dict):
            return
        url = _citation_text(value, "url", "uri", "link", "source_url") or ""
        parsed = urlparse(url)
        if (
            len(url) > 4096
            or any(ord(char) < 32 for char in url)
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or url in seen
        ):
            return
        seen.add(url)
        source_id = value.get("id") or value.get("index")
        candidates.append(
            ProviderCitation(
                url=url,
                title=_citation_text(value, "title", "name"),
                cited_text=_citation_text(
                    value, "cited_text", "snippet", "quote", "text"
                ),
                native_type=native_type,
                source_path=path,
                source_id=str(source_id)[:160] if source_id is not None else None,
            )
        )

    def add_list(value: Any, *, path: str, native_type: str) -> None:
        if not isinstance(value, list):
            return
        for index, item in enumerate(value):
            add(item, path=f"{path}/{index}", native_type=native_type)

    def add_annotations(value: Any, *, path: str) -> None:
        if not isinstance(value, list):
            return
        for index, annotation in enumerate(value):
            if not isinstance(annotation, dict):
                continue
            annotation_type = str(annotation.get("type") or "").strip().lower()
            if annotation_type not in {
                "citation",
                "url_citation",
                "web_search_citation",
            }:
                continue
            nested = annotation.get("url_citation")
            if isinstance(nested, dict):
                add(
                    nested,
                    path=f"{path}/{index}/url_citation",
                    native_type="url_citation_annotation",
                )
            else:
                add(
                    annotation,
                    path=f"{path}/{index}",
                    native_type="url_citation_annotation",
                )

    search_info_locations = ((data.get("search_info"), "/search_info"),)
    output_container = data.get("output")
    if isinstance(output_container, dict):
        search_info_locations += (
            (output_container.get("search_info"), "/output/search_info"),
        )
    for search_info, path in search_info_locations:
        if not isinstance(search_info, dict):
            continue
        add_list(
            search_info.get("search_results"),
            path=f"{path}/search_results",
            native_type="search_info_result",
        )
        add_list(
            search_info.get("sources"),
            path=f"{path}/sources",
            native_type="search_info_source",
        )

    output = data.get("output")
    if isinstance(output, list):
        for output_index, item in enumerate(output):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            if item_type == "web_search_call":
                action = item.get("action")
                if isinstance(action, dict):
                    add_list(
                        action.get("sources"),
                        path=f"/output/{output_index}/action/sources",
                        native_type="web_search_call_source",
                    )
                add(
                    item.get("source"),
                    path=f"/output/{output_index}/source",
                    native_type="web_search_call_source",
                )
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_index, block in enumerate(content):
                if not isinstance(block, dict):
                    continue
                add_annotations(
                    block.get("annotations"),
                    path=f"/output/{output_index}/content/{content_index}/annotations",
                )

    choices = data.get("choices")
    if isinstance(choices, list):
        for choice_index, choice in enumerate(choices):
            message = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(message, dict):
                continue
            add_annotations(
                message.get("annotations"),
                path=f"/choices/{choice_index}/message/annotations",
            )

    add_list(data.get("citations"), path="/citations", native_type="native_citation")
    return tuple(candidates)


def detect_web_search(
    data: Mapping[str, Any], requested: bool
) -> tuple[bool | None, str]:
    search_info = data.get("search_info")
    output_container = data.get("output")
    if not isinstance(search_info, (dict, list)) and isinstance(output_container, dict):
        search_info = output_container.get("search_info")
    if isinstance(search_info, (dict, list)):
        return True, f"{SEARCH_EVIDENCE_VERSION}:explicit_search_info"

    if isinstance(output_container, list) and any(
        isinstance(item, dict) and item.get("type") == "web_search_call"
        for item in output_container
    ):
        return True, f"{SEARCH_EVIDENCE_VERSION}:explicit_tool_call"

    usage = data.get("usage")
    if isinstance(usage, dict):
        x_tools = usage.get("x_tools")
        web_search = x_tools.get("web_search") if isinstance(x_tools, dict) else None
        count = web_search.get("count") if isinstance(web_search, dict) else None
        if isinstance(count, (int, float)) and count > 0:
            return True, f"{SEARCH_EVIDENCE_VERSION}:explicit_tool_usage"
        plugins = usage.get("plugins")
        plugin_names: list[str] = []
        if isinstance(plugins, dict):
            plugin_names.extend(str(key) for key, value in plugins.items() if value)
        elif isinstance(plugins, list):
            for plugin in plugins:
                if isinstance(plugin, str):
                    plugin_names.append(plugin)
                elif isinstance(plugin, dict):
                    plugin_names.extend(
                        str(plugin.get(key) or "") for key in ("type", "name")
                    )
        if any(
            name.strip().lower().replace("-", "_")
            in {"web_search", "web_search_preview", "internet_search"}
            for name in plugin_names
        ):
            return True, f"{SEARCH_EVIDENCE_VERSION}:explicit_plugin_usage"

    if not requested:
        return False, f"{SEARCH_EVIDENCE_VERSION}:not_requested"
    return None, f"{SEARCH_EVIDENCE_VERSION}:requested_unverifiable"


def extract_request_id(data: Mapping[str, Any], headers: Mapping[str, str]) -> str | None:
    normalized_headers = {str(key).lower(): str(value) for key, value in headers.items()}
    for candidate in (
        normalized_headers.get("x-request-id"),
        normalized_headers.get("request-id"),
        data.get("request_id"),
        data.get("id"),
    ):
        if candidate:
            return str(candidate)[:160]
    return None


def extract_usage(data: Mapping[str, Any]) -> ProviderUsage:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return ProviderUsage()

    def integer(*keys: str) -> int | None:
        for key in keys:
            value = usage.get(key)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
        return None

    input_tokens = integer("input_tokens", "prompt_tokens")
    output_tokens = integer("output_tokens", "completion_tokens")
    total_tokens = integer("total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    precision = UsagePrecision.EXACT if any(
        value is not None for value in (input_tokens, output_tokens, total_tokens)
    ) else UsagePrecision.UNKNOWN
    cost_amount: Decimal | None = None
    cost_currency: str | None = None
    raw_cost = usage.get("total_cost", usage.get("cost"))
    raw_currency = usage.get("cost_currency", usage.get("currency"))
    if isinstance(raw_currency, str) and len(raw_currency.strip()) == 3:
        try:
            parsed_cost = Decimal(str(raw_cost))
        except (InvalidOperation, ValueError, TypeError):
            parsed_cost = None
        if parsed_cost is not None and parsed_cost.is_finite() and parsed_cost >= 0:
            cost_amount = parsed_cost
            cost_currency = raw_currency.strip().upper()
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        precision=precision,
        cost_amount=cost_amount,
        cost_currency=cost_currency,
        cost_precision=(UsagePrecision.EXACT if cost_amount is not None else UsagePrecision.UNKNOWN),
        cost_source=("provider_response_billed" if cost_amount is not None else "missing"),
    )


def parse_response(
    data: Mapping[str, Any], headers: Mapping[str, str], *, search_requested: bool
) -> tuple[
    str,
    str | None,
    tuple[ProviderCitation, ...],
    bool | None,
    str,
    ProviderUsage,
]:
    search_used, search_evidence = detect_web_search(data, search_requested)
    return (
        _response_text(data),
        extract_request_id(data, headers),
        extract_citations(data),
        search_used,
        search_evidence,
        extract_usage(data),
    )
