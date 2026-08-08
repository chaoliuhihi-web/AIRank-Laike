from __future__ import annotations

from dataclasses import replace
import socket
import ssl

import pytest

import airank_outbound_security.client as outbound_client

from airank_outbound_security import (
    OutboundPolicy,
    OutboundResponse,
    OutboundSecurityError,
    SafeOutboundClient,
)


PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class FakeTransport:
    def __init__(self, responses: list[OutboundResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[object, str, dict[str, str], bytes | None]] = []

    def send(self, target, method, *, headers, body, timeout_seconds, max_response_bytes):
        self.calls.append((target, method, dict(headers), body))
        response = self.responses.pop(0)
        return replace(response, connected_ip=target.selected_ip, final_url=target.url)


def resolver_for(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return lambda *args, **kwargs: [(family, socket.SOCK_STREAM, 6, "", (address, 443))]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://localhost/path",
        "https://127.0.0.1/path",
        "https://2130706433/path",
        "https://example.com/#fragment",
        "https://example.com\\@evil.test/path",
    ],
)
def test_default_policy_rejects_unsafe_url_shapes(url: str) -> None:
    policy = OutboundPolicy(resolver=lambda *args, **kwargs: PUBLIC)
    with pytest.raises(OutboundSecurityError):
        policy.resolve(url)


@pytest.mark.parametrize(
    "address",
    [
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "192.168.1.1",
        "::1",
        "::ffff:127.0.0.1",
        "64:ff9b::7f00:1",
        "2001:db8::1",
        "fc00::1",
    ],
)
def test_policy_rejects_non_public_and_transition_addresses(address: str) -> None:
    policy = OutboundPolicy(resolver=resolver_for(address))
    with pytest.raises(OutboundSecurityError) as caught:
        policy.resolve("https://provider.example/v1")
    assert caught.value.code == "OUTBOUND_ADDRESS_FORBIDDEN"


def test_policy_requires_every_dns_answer_to_be_safe() -> None:
    def resolver(*args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]

    with pytest.raises(OutboundSecurityError):
        OutboundPolicy(resolver=resolver).resolve("https://provider.example")


def test_policy_normalizes_url_and_enforces_exact_host_allowlist() -> None:
    policy = OutboundPolicy(allowed_hosts={"Provider.Example."}, resolver=lambda *args, **kwargs: PUBLIC)
    target = policy.resolve("https://provider.example:443/v1?model=x")
    assert target.url == "https://provider.example/v1?model=x"
    assert target.selected_ip == "93.184.216.34"
    with pytest.raises(OutboundSecurityError, match="allowlisted"):
        policy.resolve("https://sub.provider.example/v1")


def test_redirect_is_revalidated_and_cross_origin_credentials_are_stripped() -> None:
    redirect = OutboundResponse(
        status=302,
        headers={"location": "https://second.example/result"},
        body=b"",
        final_url="",
        redirect_count=0,
        connected_ip="",
    )
    success = OutboundResponse(
        status=200,
        headers={},
        body=b"ok",
        final_url="",
        redirect_count=0,
        connected_ip="",
    )
    transport = FakeTransport([redirect, success])
    policy = OutboundPolicy(
        allowed_hosts={"first.example", "second.example"},
        resolver=lambda *args, **kwargs: PUBLIC,
    )
    result = SafeOutboundClient(policy, transport=transport, max_redirects=1).request(
        "GET",
        "https://first.example/start",
        headers={"Authorization": "Bearer secret", "Cookie": "sid=secret", "X-Trace": "ok"},
    )
    assert result.status == 200
    assert result.redirect_count == 1
    assert transport.calls[0][2]["Authorization"] == "Bearer secret"
    assert "Authorization" not in transport.calls[1][2]
    assert "Cookie" not in transport.calls[1][2]
    assert transport.calls[1][2]["X-Trace"] == "ok"


def test_redirect_to_private_target_is_blocked_before_second_transport_call() -> None:
    redirect = OutboundResponse(
        status=302,
        headers={"location": "https://metadata.example/latest"},
        body=b"",
        final_url="",
        redirect_count=0,
        connected_ip="",
    )
    transport = FakeTransport([redirect])

    def resolver(host, *args, **kwargs):
        value = "169.254.169.254" if host == "metadata.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443))]

    client = SafeOutboundClient(
        OutboundPolicy(resolver=resolver),
        transport=transport,
        max_redirects=1,
    )
    with pytest.raises(OutboundSecurityError) as caught:
        client.request("GET", "https://first.example/start")
    assert caught.value.code == "OUTBOUND_ADDRESS_FORBIDDEN"
    assert len(transport.calls) == 1


def test_redirect_limit_is_fail_closed() -> None:
    transport = FakeTransport(
        [
            OutboundResponse(302, {"location": "/again"}, b"", "", 0, ""),
        ]
    )
    client = SafeOutboundClient(
        OutboundPolicy(resolver=lambda *args, **kwargs: PUBLIC),
        transport=transport,
        max_redirects=0,
    )
    with pytest.raises(OutboundSecurityError) as caught:
        client.request("GET", "https://example.com/start")
    assert caught.value.code == "OUTBOUND_REDIRECT_LIMIT"


def test_https_connection_pins_validated_ip_but_preserves_tls_hostname(monkeypatch) -> None:
    target = OutboundPolicy(resolver=lambda *args, **kwargs: PUBLIC).resolve(
        "https://provider.example/v1"
    )
    raw_socket = object()
    wrapped_socket = object()
    observed: dict[str, object] = {}

    def fake_create_connection(address, timeout):
        observed["address"] = address
        observed["timeout"] = timeout
        return raw_socket

    class FakeContext:
        verify_mode = ssl.CERT_REQUIRED
        check_hostname = True

        def wrap_socket(self, sock, *, server_hostname):
            observed["raw_socket"] = sock
            observed["server_hostname"] = server_hostname
            return wrapped_socket

    monkeypatch.setattr(outbound_client.socket, "create_connection", fake_create_connection)
    connection = outbound_client._PinnedHTTPSConnection(  # noqa: SLF001 - security invariant test
        target,
        timeout=7.5,
        context=FakeContext(),
    )
    connection.connect()

    assert observed == {
        "address": ("93.184.216.34", 443),
        "timeout": 7.5,
        "raw_socket": raw_socket,
        "server_hostname": "provider.example",
    }
    assert connection.sock is wrapped_socket
