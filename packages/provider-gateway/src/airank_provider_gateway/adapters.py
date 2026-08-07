from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping
from urllib.parse import urlparse

from .models import ProviderCitation, ProviderManifest, ProviderUsage, UsagePrecision


def build_request(
    manifest: ProviderManifest,
    model: str,
    prompt: str,
    max_tokens: int,
    *,
    include_web_search: bool = True,
) -> dict[str, Any]:
    if manifest.request_kind == "responses_web_search":
        request: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "temperature": 0.2,
            "max_output_tokens": max_tokens,
        }
        if include_web_search:
            request["tools"] = [{"type": "web_search"}]
        return request
    request: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if manifest.request_kind == "chat_completions_search":
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


def _walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, (*path, str(key).lower()))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, (*path, str(index)))


def extract_citations(data: Mapping[str, Any]) -> tuple[ProviderCitation, ...]:
    candidates: list[ProviderCitation] = []
    seen: set[str] = set()
    for path, value in _walk(data):
        if not isinstance(value, dict):
            continue
        context = " ".join(path + tuple(str(value.get(key, "")).lower() for key in ("type", "name")))
        if not any(marker in context for marker in ("citation", "search", "source", "reference")):
            continue
        url = next(
            (
                str(value[key]).strip()
                for key in ("url", "uri", "link", "source_url")
                if isinstance(value.get(key), str) and str(value[key]).strip()
            ),
            "",
        )
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
            continue
        seen.add(url)
        title = next(
            (str(value[key]).strip() for key in ("title", "name") if isinstance(value.get(key), str)),
            None,
        )
        cited_text = next(
            (
                str(value[key]).strip()
                for key in ("cited_text", "snippet", "quote")
                if isinstance(value.get(key), str)
            ),
            None,
        )
        candidates.append(ProviderCitation(url=url, title=title or None, cited_text=cited_text or None))
    return tuple(candidates)


def detect_web_search(data: Mapping[str, Any], requested: bool) -> bool | None:
    serialized_keys = " ".join("/".join(path) for path, _ in _walk(data)).lower()
    if any(marker in serialized_keys for marker in ("web_search", "search_info", "url_citation")):
        return True
    for _path, value in _walk(data):
        if not isinstance(value, dict):
            continue
        marker_value = " ".join(
            str(value.get(key) or "").lower() for key in ("type", "name", "tool_name")
        )
        if any(marker in marker_value for marker in ("web_search", "search_info", "url_citation")):
            return True
    return None if requested else False


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
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        precision=precision,
    )


def parse_response(
    data: Mapping[str, Any], headers: Mapping[str, str], *, search_requested: bool
) -> tuple[str, str | None, tuple[ProviderCitation, ...], bool | None, ProviderUsage]:
    return (
        _response_text(data),
        extract_request_id(data, headers),
        extract_citations(data),
        detect_web_search(data, search_requested),
        extract_usage(data),
    )
