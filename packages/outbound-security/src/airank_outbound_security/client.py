from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import re
import socket
import ssl
from typing import Callable, Mapping, Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit


_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_AMBIGUOUS_NUMERIC_HOST = re.compile(r"^(?:0x[0-9a-f]+|[0-9.]+)$", re.IGNORECASE)
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-api-key",
    "api-key",
}
_UNSAFE_TRANSITION_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "::/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "2001::/32",
        "2002::/16",
    )
)


class OutboundSecurityError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class ResolvedTarget:
    url: str
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]
    selected_ip: str

    @property
    def origin(self) -> tuple[str, str, int]:
        return self.scheme, self.host, self.port


@dataclass(frozen=True)
class OutboundResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str
    redirect_count: int
    connected_ip: str


Resolver = Callable[..., list[tuple[object, ...]]]


class OutboundTransport(Protocol):
    def send(
        self,
        target: ResolvedTarget,
        method: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> OutboundResponse:
        ...


class OutboundPolicy:
    def __init__(
        self,
        *,
        allowed_hosts: set[str] | None = None,
        require_https: bool = True,
        allow_private: bool = False,
        resolver: Resolver = socket.getaddrinfo,
    ) -> None:
        self.allowed_hosts = {
            self._normalize_host(host) for host in (allowed_hosts or set()) if host.strip()
        }
        self.require_https = require_https
        self.allow_private = allow_private
        self.resolver = resolver

    def resolve(self, value: str) -> ResolvedTarget:
        normalized, scheme, host, port = self._normalize_url(value)
        if self.allowed_hosts and host not in self.allowed_hosts:
            raise OutboundSecurityError(
                "OUTBOUND_HOST_NOT_ALLOWED",
                "outbound target host is not allowlisted",
            )
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            addresses = (literal.compressed.lower(),)
        else:
            try:
                records = self.resolver(host, port, type=socket.SOCK_STREAM)
            except OSError as exc:
                raise OutboundSecurityError(
                    "OUTBOUND_DNS_FAILED",
                    "outbound target DNS resolution failed",
                    retryable=True,
                ) from exc
            addresses = tuple(
                dict.fromkeys(
                    str(record[4][0]).strip().lower()
                    for record in records
                    if len(record) >= 5 and record[4] and record[4][0]
                )
            )
        if not addresses:
            raise OutboundSecurityError(
                "OUTBOUND_DNS_FAILED",
                "outbound target has no resolved address",
                retryable=True,
            )
        checked: list[str] = []
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise OutboundSecurityError(
                    "OUTBOUND_ADDRESS_INVALID",
                    "outbound target resolved to an invalid address",
                ) from exc
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
                raise OutboundSecurityError(
                    "OUTBOUND_ADDRESS_FORBIDDEN",
                    "IPv4-mapped IPv6 outbound targets are forbidden",
                )
            if any(address in network for network in _UNSAFE_TRANSITION_NETWORKS):
                raise OutboundSecurityError(
                    "OUTBOUND_ADDRESS_FORBIDDEN",
                    "IPv6 transition outbound targets are forbidden",
                )
            if not self.allow_private and not address.is_global:
                raise OutboundSecurityError(
                    "OUTBOUND_ADDRESS_FORBIDDEN",
                    "outbound target resolved to a non-public address",
                )
            checked.append(address.compressed.lower())
        return ResolvedTarget(
            url=normalized,
            scheme=scheme,
            host=host,
            port=port,
            addresses=tuple(checked),
            selected_ip=checked[0],
        )

    def _normalize_url(self, value: str) -> tuple[str, str, str, int]:
        if not value or value != value.strip() or _CONTROL.search(value):
            raise OutboundSecurityError("OUTBOUND_URL_INVALID", "outbound URL is invalid")
        authority = value.split("//", 1)[1].split("/", 1)[0] if "//" in value else ""
        authority = authority.split("?", 1)[0].split("#", 1)[0]
        if "%" in authority or "\\" in authority:
            raise OutboundSecurityError(
                "OUTBOUND_URL_AMBIGUOUS",
                "outbound URL authority is ambiguous",
            )
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise OutboundSecurityError("OUTBOUND_URL_INVALID", "outbound URL port is invalid") from exc
        scheme = parsed.scheme.lower()
        allowed_schemes = {"https"} if self.require_https else {"http", "https"}
        if scheme not in allowed_schemes:
            raise OutboundSecurityError(
                "OUTBOUND_SCHEME_FORBIDDEN",
                "outbound URL must use HTTPS" if self.require_https else "outbound URL must use HTTP(S)",
            )
        if parsed.username is not None or parsed.password is not None:
            raise OutboundSecurityError(
                "OUTBOUND_USERINFO_FORBIDDEN",
                "outbound URL must not contain credentials",
            )
        if parsed.fragment:
            raise OutboundSecurityError(
                "OUTBOUND_FRAGMENT_FORBIDDEN",
                "outbound URL fragments are forbidden",
            )
        host = self._normalize_host(parsed.hostname or "")
        if not host:
            raise OutboundSecurityError("OUTBOUND_HOST_INVALID", "outbound URL has no valid host")
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise OutboundSecurityError(
                "OUTBOUND_ADDRESS_FORBIDDEN",
                "localhost and local network targets are forbidden",
            )
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if _AMBIGUOUS_NUMERIC_HOST.fullmatch(host):
                raise OutboundSecurityError(
                    "OUTBOUND_HOST_AMBIGUOUS",
                    "ambiguous numeric outbound hosts are forbidden",
                )
            labels = host.split(".")
            if len(host) > 253 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
                raise OutboundSecurityError(
                    "OUTBOUND_HOST_INVALID",
                    "outbound URL host is invalid",
                )
        selected_port = port or (443 if scheme == "https" else 80)
        if selected_port < 1 or selected_port > 65535:
            raise OutboundSecurityError("OUTBOUND_URL_INVALID", "outbound URL port is invalid")
        display_host = f"[{host}]" if ":" in host else host
        default_port = 443 if scheme == "https" else 80
        netloc = display_host if selected_port == default_port else f"{display_host}:{selected_port}"
        normalized = urlunsplit((scheme, netloc, parsed.path or "", parsed.query or "", ""))
        return normalized, scheme, host, selected_port

    @staticmethod
    def _normalize_host(value: str) -> str:
        host = value.strip().lower().rstrip(".")
        if not host:
            return ""
        try:
            host.encode("ascii")
        except UnicodeEncodeError as exc:
            raise OutboundSecurityError(
                "OUTBOUND_HOST_INVALID",
                "outbound URL host must be ASCII",
            ) from exc
        return host


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, target: ResolvedTarget, *, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(target.host, target.port, timeout=timeout, context=context)
        self._target = target

    def connect(self) -> None:
        raw = socket.create_connection((self._target.selected_ip, self._target.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self._target.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, target: ResolvedTarget, *, timeout: float) -> None:
        super().__init__(target.host, target.port, timeout=timeout)
        self._target = target

    def connect(self) -> None:
        self.sock = socket.create_connection((self._target.selected_ip, self._target.port), self.timeout)


class PinnedStdlibTransport:
    def __init__(self, *, tls_context: ssl.SSLContext | None = None) -> None:
        self.tls_context = tls_context or ssl.create_default_context()

    def send(
        self,
        target: ResolvedTarget,
        method: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> OutboundResponse:
        connection: http.client.HTTPConnection
        if target.scheme == "https":
            connection = _PinnedHTTPSConnection(
                target,
                timeout=timeout_seconds,
                context=self.tls_context,
            )
        else:
            connection = _PinnedHTTPConnection(target, timeout=timeout_seconds)
        path = urlsplit(target.url)
        request_target = urlunsplit(("", "", path.path or "/", path.query, ""))
        safe_headers = {str(key): str(value) for key, value in headers.items()}
        safe_headers["Host"] = target.host if target.port in {80, 443} else f"{target.host}:{target.port}"
        safe_headers["Accept-Encoding"] = "identity"
        safe_headers["Connection"] = "close"
        try:
            connection.request(method, request_target, body=body, headers=safe_headers)
            response = connection.getresponse()
            response_headers = {key.lower(): value for key, value in response.getheaders()}
            encoding = response_headers.get("content-encoding", "").strip().lower()
            if encoding not in {"", "identity"}:
                raise OutboundSecurityError(
                    "OUTBOUND_ENCODING_FORBIDDEN",
                    "encoded outbound responses are forbidden",
                )
            declared = response_headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > max_response_bytes:
                raise OutboundSecurityError(
                    "OUTBOUND_RESPONSE_TOO_LARGE",
                    "outbound response exceeds the configured byte limit",
                )
            payload = response.read(max_response_bytes + 1)
            if len(payload) > max_response_bytes:
                raise OutboundSecurityError(
                    "OUTBOUND_RESPONSE_TOO_LARGE",
                    "outbound response exceeds the configured byte limit",
                )
            return OutboundResponse(
                status=int(response.status),
                headers=response_headers,
                body=payload,
                final_url=target.url,
                redirect_count=0,
                connected_ip=target.selected_ip,
            )
        except OutboundSecurityError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise OutboundSecurityError(
                "OUTBOUND_NETWORK_FAILED",
                f"outbound request failed: {type(exc).__name__}",
                retryable=True,
            ) from exc
        finally:
            connection.close()


class SafeOutboundClient:
    def __init__(
        self,
        policy: OutboundPolicy,
        *,
        transport: OutboundTransport | None = None,
        timeout_seconds: float = 30.0,
        max_response_bytes: int = 2_000_000,
        max_redirects: int = 0,
    ) -> None:
        if max_response_bytes < 1:
            raise ValueError("max_response_bytes must be positive")
        if max_redirects < 0 or max_redirects > 3:
            raise ValueError("max_redirects must be between 0 and 3")
        self.policy = policy
        self.transport = transport or PinnedStdlibTransport()
        self.timeout_seconds = max(1.0, timeout_seconds)
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
    ) -> OutboundResponse:
        current_method = method.upper()
        if current_method not in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"}:
            raise OutboundSecurityError(
                "OUTBOUND_METHOD_FORBIDDEN",
                "outbound HTTP method is forbidden",
            )
        current_url = url
        current_headers = {str(key): str(value) for key, value in (headers or {}).items()}
        current_body = body
        previous: ResolvedTarget | None = None
        for redirect_count in range(self.max_redirects + 1):
            target = self.policy.resolve(current_url)
            if previous is not None and previous.origin != target.origin:
                current_headers = {
                    key: value
                    for key, value in current_headers.items()
                    if key.lower() not in _SENSITIVE_HEADERS
                }
            response = self.transport.send(
                target,
                current_method,
                headers=current_headers,
                body=current_body,
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=self.max_response_bytes,
            )
            if response.status not in {301, 302, 303, 307, 308}:
                return OutboundResponse(
                    status=response.status,
                    headers=response.headers,
                    body=response.body,
                    final_url=target.url,
                    redirect_count=redirect_count,
                    connected_ip=target.selected_ip,
                )
            location = str(response.headers.get("location") or "").strip()
            if not location:
                return response
            if redirect_count >= self.max_redirects:
                raise OutboundSecurityError(
                    "OUTBOUND_REDIRECT_LIMIT",
                    "outbound redirect limit exceeded",
                )
            previous = target
            current_url = urljoin(target.url, location)
            if response.status == 303 or (response.status in {301, 302} and current_method == "POST"):
                current_method = "GET"
                current_body = None
                current_headers = {
                    key: value
                    for key, value in current_headers.items()
                    if key.lower() not in {"content-length", "content-type", "transfer-encoding"}
                }
        raise AssertionError("redirect loop escaped configured bound")
