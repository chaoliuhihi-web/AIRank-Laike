from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DirectoryHttpGet = Callable[[str, Mapping[str, str], float], Mapping[str, Any]]


class YudaoDirectoryError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class YudaoReviewerDirectoryConfig:
    base_url: str | None
    bearer_token: str | None
    tenant_id: str | None
    timeout_seconds: float = 5.0
    page_size: int = 100
    max_members: int = 500
    production: bool = False

    @classmethod
    def from_env(
        cls, env: Mapping[str, str] | None = None
    ) -> "YudaoReviewerDirectoryConfig":
        source = env or os.environ
        return cls(
            base_url=_clean(source.get("YUDAO_REVIEW_DIRECTORY_BASE_URL"))
            or _clean(source.get("YUDAO_BASE_URL")),
            bearer_token=_clean(source.get("YUDAO_REVIEW_DIRECTORY_BEARER_TOKEN"))
            or _clean(source.get("YUDAO_BEARER_TOKEN"))
            or _clean(source.get("YUDAO_TOKEN")),
            tenant_id=_clean(source.get("YUDAO_TENANT_ID")),
            timeout_seconds=_bounded_float(
                source.get("YUDAO_REVIEW_DIRECTORY_TIMEOUT_SECONDS"), 5.0, 0.5, 30.0
            ),
            page_size=_bounded_int(
                source.get("YUDAO_REVIEW_DIRECTORY_PAGE_SIZE"), 100, 1, 100
            ),
            max_members=_bounded_int(
                source.get("YUDAO_REVIEW_DIRECTORY_MAX_MEMBERS"), 500, 1, 2_000
            ),
            production=str(source.get("AIRANK_ENV") or "local").strip().lower()
            == "production",
        )


@dataclass(frozen=True)
class YudaoReviewer:
    user_id: str
    username: str | None
    display_name: str | None
    department_id: str
    enabled: bool

    def to_record(self) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "department_id": self.department_id,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class YudaoReviewerDirectorySnapshot:
    department_id: str
    department_name: str
    members: tuple[YudaoReviewer, ...]
    response_sha256: str
    endpoint_host: str


class YudaoReviewerDirectoryClient:
    def __init__(
        self,
        config: YudaoReviewerDirectoryConfig | None = None,
        *,
        http_get: DirectoryHttpGet | None = None,
    ) -> None:
        self.config = config or YudaoReviewerDirectoryConfig.from_env()
        self.http_get = http_get or default_directory_http_get

    def fetch_department(self, department_id: str) -> YudaoReviewerDirectorySnapshot:
        normalized_department_id = str(department_id or "").strip()
        if not normalized_department_id or len(normalized_department_id) > 128:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_DEPARTMENT_INVALID",
                "Yudao department id is invalid",
                retryable=False,
            )
        base_url, endpoint_host = self._validated_base_url()
        headers = self._headers()
        department_payload = self._get(
            f"{base_url}/admin-api/system/dept/get?"
            + urlencode({"id": normalized_department_id}),
            headers,
        )
        department_data = _business_data(
            department_payload,
            code="YUDAO_REVIEW_DIRECTORY_DEPARTMENT_FAILED",
            expected_type=dict,
        )
        if str(department_data.get("id") or "") != normalized_department_id:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_DEPARTMENT_NOT_FOUND",
                "Yudao department response did not match the requested id",
                retryable=False,
            )
        department_name = str(department_data.get("name") or "").strip()
        if not department_name:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
                "Yudao department name is missing",
                retryable=False,
            )

        members: dict[str, YudaoReviewer] = {}
        total = None
        page_no = 1
        while total is None or len(members) < total:
            page_payload = self._get(
                f"{base_url}/admin-api/system/user/page?"
                + urlencode(
                    {
                        "pageNo": page_no,
                        "pageSize": self.config.page_size,
                        "deptId": normalized_department_id,
                        "status": 0,
                    }
                ),
                headers,
            )
            page_data = _business_data(
                page_payload,
                code="YUDAO_REVIEW_DIRECTORY_USERS_FAILED",
                expected_type=dict,
            )
            raw_list = page_data.get("list")
            raw_total = page_data.get("total")
            if not isinstance(raw_list, list) or not isinstance(raw_total, int):
                raise YudaoDirectoryError(
                    "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
                    "Yudao user page is missing list or total",
                    retryable=False,
                )
            if raw_total < 0 or raw_total > self.config.max_members:
                raise YudaoDirectoryError(
                    "YUDAO_REVIEW_DIRECTORY_TOO_LARGE",
                    "Yudao reviewer department exceeds the configured member limit",
                    retryable=False,
                )
            total = raw_total
            for item in raw_list:
                reviewer = _parse_reviewer(item, normalized_department_id)
                existing = members.get(reviewer.user_id)
                if existing is not None and existing != reviewer:
                    raise YudaoDirectoryError(
                        "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
                        "Yudao returned conflicting records for one reviewer",
                        retryable=False,
                    )
                members[reviewer.user_id] = reviewer
            if len(members) > self.config.max_members:
                raise YudaoDirectoryError(
                    "YUDAO_REVIEW_DIRECTORY_TOO_LARGE",
                    "Yudao reviewer department exceeds the configured member limit",
                    retryable=False,
                )
            if not raw_list:
                break
            page_no += 1
            if page_no > (self.config.max_members // self.config.page_size) + 2:
                raise YudaoDirectoryError(
                    "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
                    "Yudao pagination did not converge",
                    retryable=False,
                )
        if total is None or len(members) != total:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
                "Yudao user page count does not match the declared total",
                retryable=False,
            )
        ordered_members = tuple(members[key] for key in sorted(members))
        canonical = {
            "department_id": normalized_department_id,
            "department_name": department_name,
            "members": [member.to_record() for member in ordered_members],
        }
        response_sha256 = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return YudaoReviewerDirectorySnapshot(
            department_id=normalized_department_id,
            department_name=department_name,
            members=ordered_members,
            response_sha256=response_sha256,
            endpoint_host=endpoint_host,
        )

    def _validated_base_url(self) -> tuple[str, str]:
        base_url = str(self.config.base_url or "").strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_NOT_CONFIGURED",
                "Yudao reviewer directory base URL is not configured",
                retryable=False,
            )
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_NOT_CONFIGURED",
                "Yudao reviewer directory base URL must not contain credentials or query data",
                retryable=False,
            )
        if self.config.production and parsed.scheme != "https":
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_INSECURE_TRANSPORT",
                "Production Yudao reviewer directory requires HTTPS",
                retryable=False,
            )
        return base_url, parsed.hostname.lower()

    def _headers(self) -> dict[str, str]:
        token = str(self.config.bearer_token or "").strip()
        tenant_id = str(self.config.tenant_id or "").strip()
        if not token or not tenant_id:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_NOT_CONFIGURED",
                "Yudao reviewer directory token and tenant are required",
                retryable=False,
            )
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "tenant-id": tenant_id,
        }

    def _get(self, url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        try:
            return self.http_get(url, headers, self.config.timeout_seconds)
        except YudaoDirectoryError:
            raise
        except HTTPError as exc:
            code = (
                "YUDAO_REVIEW_DIRECTORY_AUTH_FAILED"
                if exc.code in {401, 403}
                else "YUDAO_REVIEW_DIRECTORY_UPSTREAM_FAILED"
            )
            raise YudaoDirectoryError(
                code,
                f"Yudao reviewer directory returned HTTP {exc.code}",
                retryable=exc.code >= 500 or exc.code == 429,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_UNAVAILABLE",
                "Yudao reviewer directory is unavailable",
                retryable=True,
            ) from exc
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise YudaoDirectoryError(
                "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
                "Yudao reviewer directory returned invalid JSON",
                retryable=False,
            ) from exc


def default_directory_http_get(
    url: str, headers: Mapping[str, str], timeout_seconds: float
) -> Mapping[str, Any]:
    request = Request(url, headers=dict(headers), method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        raw_body = response.read().decode("utf-8")
    payload = json.loads(raw_body) if raw_body else {}
    if not isinstance(payload, dict):
        raise ValueError("Yudao response must be an object")
    return payload


def _business_data(
    payload: Mapping[str, Any], *, code: str, expected_type: type
) -> Any:
    if payload.get("code") not in {0, "0", None}:
        raise YudaoDirectoryError(
            code,
            "Yudao reviewer directory business request failed",
            retryable=False,
        )
    data = payload.get("data")
    if not isinstance(data, expected_type):
        raise YudaoDirectoryError(
            "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
            "Yudao reviewer directory response data is invalid",
            retryable=False,
        )
    return data


def _parse_reviewer(value: object, requested_department_id: str) -> YudaoReviewer:
    if not isinstance(value, Mapping):
        raise YudaoDirectoryError(
            "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
            "Yudao reviewer record is invalid",
            retryable=False,
        )
    user_id = str(value.get("id") or "").strip()
    department_id = str(value.get("deptId") or "").strip()
    if not user_id or not department_id:
        raise YudaoDirectoryError(
            "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
            "Yudao reviewer record is missing identity fields",
            retryable=False,
        )
    status = value.get("status")
    if status not in {0, "0"}:
        raise YudaoDirectoryError(
            "YUDAO_REVIEW_DIRECTORY_RESPONSE_INVALID",
            "Yudao returned a disabled reviewer in the enabled-user page",
            retryable=False,
        )
    return YudaoReviewer(
        user_id=user_id[:128],
        username=_limited_optional(value.get("username"), 160),
        display_name=_limited_optional(value.get("nickname"), 160),
        department_id=department_id[:128] or requested_department_id,
        enabled=True,
    )


def _clean(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _limited_optional(value: object, maximum: int) -> str | None:
    normalized = _clean(value)
    return normalized[:maximum] if normalized else None


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value or default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _bounded_float(
    value: object, default: float, minimum: float, maximum: float
) -> float:
    try:
        parsed = float(str(value or default))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))
