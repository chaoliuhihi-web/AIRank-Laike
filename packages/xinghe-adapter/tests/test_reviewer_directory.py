from __future__ import annotations

from urllib.error import HTTPError

import pytest

from airank_xinghe_adapter import (
    YudaoDirectoryError,
    YudaoReviewerDirectoryClient,
    YudaoReviewerDirectoryConfig,
)


def test_directory_fetches_department_and_paginates_without_sensitive_fields() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_http(url: str, headers: dict[str, str], timeout: float):
        assert timeout == 3.0
        calls.append((url, dict(headers)))
        if "/system/dept/get" in url:
            return {"code": 0, "data": {"id": 42, "name": "证据复核组"}}
        page = 1 if "pageNo=1" in url else 2
        records = (
            [
                {
                    "id": 8,
                    "username": "reviewer-8",
                    "nickname": "复核员八号",
                    "deptId": 42,
                    "status": 0,
                    "mobile": "must-not-be-copied",
                    "email": "must-not-be-copied@example.test",
                }
            ]
            if page == 1
            else [
                {
                    "id": 9,
                    "username": "reviewer-9",
                    "nickname": "复核员九号",
                    "deptId": 43,
                    "status": 0,
                }
            ]
        )
        return {"code": 0, "data": {"list": records, "total": 2}}

    client = YudaoReviewerDirectoryClient(
        YudaoReviewerDirectoryConfig(
            base_url="https://yudao.example.test",
            bearer_token="secret-token",
            tenant_id="7",
            timeout_seconds=3.0,
            page_size=1,
            max_members=10,
            production=True,
        ),
        http_get=fake_http,
    )

    snapshot = client.fetch_department("42")

    assert snapshot.department_name == "证据复核组"
    assert snapshot.endpoint_host == "yudao.example.test"
    assert [item.user_id for item in snapshot.members] == ["8", "9"]
    assert snapshot.members[1].department_id == "43"
    assert len(snapshot.response_sha256) == 64
    assert len(calls) == 3
    assert all(headers["Authorization"] == "Bearer secret-token" for _, headers in calls)
    assert all(headers["tenant-id"] == "7" for _, headers in calls)
    assert all("mobile" not in item.to_record() for item in snapshot.members)
    assert all("email" not in item.to_record() for item in snapshot.members)


def test_directory_rejects_insecure_production_transport_before_network() -> None:
    client = YudaoReviewerDirectoryClient(
        YudaoReviewerDirectoryConfig(
            base_url="http://127.0.0.1:48080",
            bearer_token="token",
            tenant_id="1",
            production=True,
        ),
        http_get=lambda *_args: pytest.fail("network must not be called"),
    )

    with pytest.raises(YudaoDirectoryError) as blocked:
        client.fetch_department("1")

    assert blocked.value.code == "YUDAO_REVIEW_DIRECTORY_INSECURE_TRANSPORT"
    assert blocked.value.retryable is False


def test_directory_blocks_missing_credentials_and_oversized_groups() -> None:
    missing = YudaoReviewerDirectoryClient(
        YudaoReviewerDirectoryConfig(
            base_url="https://yudao.example.test",
            bearer_token=None,
            tenant_id="1",
        )
    )
    with pytest.raises(YudaoDirectoryError) as not_configured:
        missing.fetch_department("1")
    assert not_configured.value.code == "YUDAO_REVIEW_DIRECTORY_NOT_CONFIGURED"

    def fake_http(url: str, _headers: dict[str, str], _timeout: float):
        if "/system/dept/get" in url:
            return {"code": 0, "data": {"id": 1, "name": "超大部门"}}
        return {"code": 0, "data": {"list": [], "total": 11}}

    oversized = YudaoReviewerDirectoryClient(
        YudaoReviewerDirectoryConfig(
            base_url="https://yudao.example.test",
            bearer_token="token",
            tenant_id="1",
            max_members=10,
        ),
        http_get=fake_http,
    )
    with pytest.raises(YudaoDirectoryError) as too_large:
        oversized.fetch_department("1")
    assert too_large.value.code == "YUDAO_REVIEW_DIRECTORY_TOO_LARGE"


def test_directory_maps_auth_and_network_failures_without_leaking_token() -> None:
    def auth_failure(_url: str, _headers: dict[str, str], _timeout: float):
        raise HTTPError("https://yudao.example.test", 403, "forbidden", {}, None)

    client = YudaoReviewerDirectoryClient(
        YudaoReviewerDirectoryConfig(
            base_url="https://yudao.example.test",
            bearer_token="top-secret-token",
            tenant_id="1",
        ),
        http_get=auth_failure,
    )
    with pytest.raises(YudaoDirectoryError) as denied:
        client.fetch_department("1")
    assert denied.value.code == "YUDAO_REVIEW_DIRECTORY_AUTH_FAILED"
    assert "top-secret-token" not in str(denied.value)

    client = YudaoReviewerDirectoryClient(
        YudaoReviewerDirectoryConfig(
            base_url="https://yudao.example.test",
            bearer_token="top-secret-token",
            tenant_id="1",
        ),
        http_get=lambda *_args: (_ for _ in ()).throw(TimeoutError()),
    )
    with pytest.raises(YudaoDirectoryError) as unavailable:
        client.fetch_department("1")
    assert unavailable.value.code == "YUDAO_REVIEW_DIRECTORY_UNAVAILABLE"
    assert unavailable.value.retryable is True
