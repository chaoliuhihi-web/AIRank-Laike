#!/usr/bin/env python3
"""Fail closed when an AIRank production process is misconfigured.

The preflight is deliberately side-effect free. It validates deployment shape
and secret metadata without printing secret values. Network and data-plane
proofs remain the responsibility of the release-readiness gate.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence
from urllib.parse import parse_qs, urlparse


TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"", "0", "false", "no", "off"}
PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "example",
    "placeholder",
    "replace-me",
    "replace_me",
    "your-",
    "<",
    ">",
)
PROVIDER_NAMES = ("qianwen", "doubao", "kimi", "deepseek")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,63}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
IMMUTABLE_IMAGE_RE = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9._:/-]*@)?sha256:[0-9a-f]{64}$"
)


@dataclass(frozen=True)
class PreflightResult:
    role: str
    checks: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers

    def to_record(self) -> dict[str, object]:
        return {
            "status": "ready" if self.ready else "blocked",
            "role": self.role,
            "checks": list(self.checks),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


def _clean(source: Mapping[str, str], name: str) -> str:
    return str(source.get(name) or "").strip()


def _enabled(source: Mapping[str, str], name: str) -> bool:
    return _clean(source, name).lower() in TRUE_VALUES


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _absolute_https(value: str) -> bool:
    parsed = urlparse(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def _key_map(
    source: Mapping[str, str],
    *,
    active_name: str,
    mapping_name: str,
    blockers: list[str],
) -> tuple[str, dict[str, bytes]]:
    active_id = _clean(source, active_name)
    raw_mapping = _clean(source, mapping_name)
    if not active_id or not KEY_ID_RE.fullmatch(active_id):
        blockers.append(f"{active_name} must contain a valid non-placeholder key id")
    try:
        parsed = json.loads(raw_mapping)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict) or not parsed:
        blockers.append(f"{mapping_name} must be a non-empty JSON object")
        return active_id, {}
    decoded: dict[str, bytes] = {}
    for key_id, encoded in parsed.items():
        if not isinstance(key_id, str) or not KEY_ID_RE.fullmatch(key_id):
            blockers.append(f"{mapping_name} contains an invalid key id")
            continue
        if not isinstance(encoded, str) or _is_placeholder(encoded):
            blockers.append(f"{mapping_name}[{key_id}] is missing real key material")
            continue
        try:
            material = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            blockers.append(f"{mapping_name}[{key_id}] is not valid Base64")
            continue
        if len(material) != 32:
            blockers.append(f"{mapping_name}[{key_id}] must decode to exactly 32 bytes")
            continue
        decoded[key_id] = material
    if active_id and active_id not in decoded:
        blockers.append(f"{active_name} is not present in {mapping_name}")
    if len(set(decoded.values())) != len(decoded):
        blockers.append(f"{mapping_name} reuses key material across key ids")
    return active_id, decoded


def _validate_database(source: Mapping[str, str], blockers: list[str]) -> None:
    value = _clean(source, "AIRANK_DATABASE_URL")
    parsed = urlparse(value)
    single_node = _enabled(source, "AIRANK_SINGLE_NODE_MODE")
    if parsed.scheme != "mysql+pymysql" or not parsed.hostname or not parsed.path.strip("/"):
        blockers.append("AIRANK_DATABASE_URL must be a complete mysql+pymysql URL")
        return
    if _is_placeholder(parsed.hostname):
        blockers.append("AIRANK_DATABASE_URL must use the final production database host")
    if not parsed.username or not parsed.password or _is_placeholder(parsed.password):
        blockers.append("AIRANK_DATABASE_URL must use a non-placeholder deployment credential")
    bundled_hosts = {"127.0.0.1", "localhost", "mysql", "db", "airank-db"}
    if parsed.hostname in bundled_hosts and not (
        single_node and parsed.hostname == "airank-db"
    ):
        blockers.append("AIRANK_DATABASE_URL must not target a local or bundled development database")
    if single_node and parsed.hostname != "airank-db":
        blockers.append(
            "AIRANK_SINGLE_NODE_MODE requires the dedicated TLS hostname airank-db"
        )
    query = {key: values[-1].lower() for key, values in parse_qs(parsed.query).items() if values}
    verify_mode = _clean(source, "AIRANK_DATABASE_TLS_VERIFY_MODE").lower()
    if not query.get("ssl_ca") or verify_mode != "identity":
        blockers.append(
            "AIRANK_DATABASE_URL must provide ssl_ca and "
            "AIRANK_DATABASE_TLS_VERIFY_MODE must be identity"
        )
    if "ssl_verify_cert" in query or "ssl_verify_identity" in query:
        blockers.append(
            "AIRANK_DATABASE_URL must not use ssl_verify_cert/ssl_verify_identity query "
            "flags because SQLAlchemy would overwrite the PyMySQL CA context"
        )


def _validate_object_storage(source: Mapping[str, str], blockers: list[str]) -> None:
    driver = _clean(source, "AIRANK_OBJECT_STORAGE_DRIVER").lower()
    endpoint = _clean(source, "AIRANK_S3_ENDPOINT_URL")
    bucket = _clean(source, "AIRANK_S3_BUCKET")
    if driver not in {"s3", "minio"}:
        blockers.append("AIRANK_OBJECT_STORAGE_DRIVER must be s3 or minio")
    if endpoint and (not _absolute_https(endpoint) or _is_placeholder(endpoint)):
        blockers.append("AIRANK_S3_ENDPOINT_URL must be the final absolute HTTPS URL")
    if driver == "minio" and not endpoint:
        blockers.append("AIRANK_S3_ENDPOINT_URL is required for minio")
    if not BUCKET_RE.fullmatch(bucket) or _is_placeholder(bucket):
        blockers.append("AIRANK_S3_BUCKET must be a valid non-placeholder bucket name")
    if _enabled(source, "AIRANK_S3_ALLOW_HTTP"):
        blockers.append("AIRANK_S3_ALLOW_HTTP must be false in production")
    access_key = _clean(source, "AIRANK_S3_ACCESS_KEY_ID")
    secret_key = _clean(source, "AIRANK_S3_SECRET_ACCESS_KEY")
    if bool(access_key) != bool(secret_key):
        blockers.append("AIRANK_S3_ACCESS_KEY_ID and AIRANK_S3_SECRET_ACCESS_KEY must be supplied together")
    if any(_is_placeholder(value) for value in (access_key, secret_key) if value):
        blockers.append("object-storage credentials contain placeholder material")
    timeout_value = _clean(source, "AIRANK_S3_TIMEOUT_SECONDS") or "10"
    try:
        timeout_seconds = float(timeout_value)
    except ValueError:
        timeout_seconds = 0
    if timeout_seconds < 1 or timeout_seconds > 300:
        blockers.append("AIRANK_S3_TIMEOUT_SECONDS must be between 1 and 300")


def _validate_auth(source: Mapping[str, str], blockers: list[str]) -> None:
    if _clean(source, "AIRANK_API_AUTH_ENFORCEMENT").lower() != "required":
        blockers.append("AIRANK_API_AUTH_ENFORCEMENT must be required")
    if _clean(source, "AIRANK_AUTH_MODE").lower() != "yudao":
        blockers.append("AIRANK_AUTH_MODE must be yudao")
    if _clean(source, "AIRANK_TENANT_RESOLUTION_MODE").lower() != "database":
        blockers.append("AIRANK_TENANT_RESOLUTION_MODE must be database")
    if _clean(source, "AIRANK_DEFAULT_TENANT_ID"):
        blockers.append("AIRANK_DEFAULT_TENANT_ID must be unset in production")
    base_url = _clean(source, "YUDAO_BASE_URL").rstrip("/")
    if not _absolute_https(base_url) or _is_placeholder(base_url):
        blockers.append("YUDAO_BASE_URL must be the final absolute HTTPS URL")
    for name in ("YUDAO_PERMISSION_INFO_URL", "YUDAO_MODEL_RESOLVE_URL"):
        endpoint = _clean(source, name)
        if not _absolute_https(endpoint) or _is_placeholder(endpoint):
            blockers.append(f"{name} must be the final absolute HTTPS URL")
            continue
        if base_url and urlparse(endpoint).hostname != urlparse(base_url).hostname:
            blockers.append(f"{name} must use the YUDAO_BASE_URL host")
    token = _clean(source, "YUDAO_BEARER_TOKEN")
    if not token or _is_placeholder(token):
        blockers.append("YUDAO_BEARER_TOKEN must be injected by the production secret manager")
    if _clean(source, "AIRANK_DEV_PERMISSIONS"):
        blockers.append("AIRANK_DEV_PERMISSIONS must be unset in production")
    tenant_provider_permission = _clean(source, "AIRANK_PROVIDER_ADMIN_PERMISSION")
    platform_provider_permission = _clean(
        source, "AIRANK_PROVIDER_PLATFORM_ADMIN_PERMISSION"
    )
    if not tenant_provider_permission:
        blockers.append("AIRANK_PROVIDER_ADMIN_PERMISSION must be configured")
    if not platform_provider_permission:
        blockers.append("AIRANK_PROVIDER_PLATFORM_ADMIN_PERMISSION must be configured")
    if tenant_provider_permission and tenant_provider_permission == platform_provider_permission:
        blockers.append("tenant and platform Provider permissions must be different")


def _validate_single_node(source: Mapping[str, str], blockers: list[str]) -> None:
    if not _enabled(source, "AIRANK_SINGLE_NODE_MODE"):
        return
    for name in (
        "AIRANK_BACKEND_IMAGE",
        "AIRANK_WEB_IMAGE",
        "AIRANK_MYSQL_IMAGE",
        "AIRANK_MINIO_IMAGE",
        "AIRANK_NGINX_IMAGE",
    ):
        if not IMMUTABLE_IMAGE_RE.fullmatch(_clean(source, name)):
            blockers.append(f"{name} must use an immutable sha256 image reference")
    for name in ("AIRANK_DATA_ROOT", "AIRANK_SECRET_ROOT"):
        value = _clean(source, name)
        normalized = os.path.normpath(value)
        if not value.startswith("/home/www1/") or normalized != value:
            blockers.append(f"{name} must be a normalized absolute path on the data disk")
    if _clean(source, "AIRANK_DATA_ROOT") == _clean(source, "AIRANK_SECRET_ROOT"):
        blockers.append("AIRANK_DATA_ROOT and AIRANK_SECRET_ROOT must be different")
    if _clean(source, "AIRANK_OBJECT_STORAGE_DRIVER").lower() != "minio":
        blockers.append("AIRANK_SINGLE_NODE_MODE requires the dedicated MinIO driver")
    if urlparse(_clean(source, "AIRANK_S3_ENDPOINT_URL")).hostname != "airank-objects":
        blockers.append("AIRANK_SINGLE_NODE_MODE requires the TLS hostname airank-objects")
    if urlparse(_clean(source, "YUDAO_BASE_URL")).hostname != "airank-yudao":
        blockers.append("AIRANK_SINGLE_NODE_MODE requires the TLS hostname airank-yudao")


def _validate_provider_runtime(
    source: Mapping[str, str],
    blockers: list[str],
    warnings: list[str],
    *,
    role: str,
) -> None:
    mode = _clean(source, "AIRANK_PROVIDER_MODE").lower()
    if mode not in {"api", "browser"}:
        blockers.append("AIRANK_PROVIDER_MODE must be api or browser; mock/dev modes are forbidden")
    if _clean(source, "AIRANK_SCAN_DISPATCH_MODE").lower() != "worker":
        blockers.append("AIRANK_SCAN_DISPATCH_MODE must be worker")
    if _enabled(source, "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS"):
        blockers.append("AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS must be false in production")
    credentials_rotated = _enabled(
        source, "AIRANK_COMPROMISED_CREDENTIALS_ROTATED"
    )
    quarantined = {
        value.strip().lower()
        for value in _clean(
            source, "AIRANK_UNROTATED_PROVIDER_CREDENTIALS_QUARANTINED"
        ).split(",")
        if value.strip()
    }
    unknown_quarantined = quarantined - set(PROVIDER_NAMES)
    if unknown_quarantined:
        blockers.append(
            "AIRANK_UNROTATED_PROVIDER_CREDENTIALS_QUARANTINED contains unsupported providers"
        )
    quarantine_valid = bool(quarantined) and not unknown_quarantined
    for provider in sorted(quarantined & set(PROVIDER_NAMES)):
        prefix = provider.upper()
        if not _enabled(source, f"{prefix}_PROVIDER_DISABLED"):
            blockers.append(
                f"{prefix}_PROVIDER_DISABLED must be true while its exposed credential is quarantined"
            )
            quarantine_valid = False
        if _clean(source, f"{prefix}_API_KEY"):
            blockers.append(
                f"{prefix}_API_KEY must be empty while its exposed credential is quarantined"
            )
            quarantine_valid = False
    temporarily_enabled = {
        value.strip().lower()
        for value in _clean(
            source,
            "AIRANK_UNROTATED_PROVIDER_CREDENTIALS_TEMPORARILY_ENABLED",
        ).split(",")
        if value.strip()
    }
    unknown_temporarily_enabled = temporarily_enabled - set(PROVIDER_NAMES)
    if unknown_temporarily_enabled:
        blockers.append(
            "AIRANK_UNROTATED_PROVIDER_CREDENTIALS_TEMPORARILY_ENABLED contains unsupported providers"
        )
    if quarantined & temporarily_enabled:
        blockers.append(
            "an unrotated Provider cannot be both quarantined and temporarily enabled"
        )
    temporary_exception_valid = (
        bool(temporarily_enabled)
        and not unknown_temporarily_enabled
        and not (quarantined & temporarily_enabled)
    )
    for provider in sorted(temporarily_enabled & set(PROVIDER_NAMES)):
        prefix = provider.upper()
        if _enabled(source, f"{prefix}_PROVIDER_DISABLED"):
            blockers.append(
                f"{prefix}_PROVIDER_DISABLED must be false while the temporary experience exception is active"
            )
            temporary_exception_valid = False
        if not _clean(source, f"{prefix}_API_KEY"):
            blockers.append(
                f"{prefix}_API_KEY must be injected while the temporary experience exception is active"
            )
            temporary_exception_valid = False
    if temporarily_enabled:
        expires_at = _clean(
            source,
            "AIRANK_UNROTATED_PROVIDER_CREDENTIALS_EXCEPTION_EXPIRES_AT",
        )
        try:
            parsed_expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if parsed_expiry.tzinfo is None:
                raise ValueError
            expiry = parsed_expiry.astimezone(timezone.utc)
        except ValueError:
            expiry = None
            blockers.append(
                "AIRANK_UNROTATED_PROVIDER_CREDENTIALS_EXCEPTION_EXPIRES_AT must be an ISO-8601 UTC timestamp"
            )
            temporary_exception_valid = False
        if expiry is not None:
            now = datetime.now(timezone.utc)
            if expiry <= now:
                blockers.append("temporary unrotated Provider credential exception has expired")
                temporary_exception_valid = False
            elif expiry > now + timedelta(days=14):
                blockers.append(
                    "temporary unrotated Provider credential exception must expire within 14 days"
                )
                temporary_exception_valid = False
    if not credentials_rotated:
        if role == "release" or not (
            quarantine_valid or temporary_exception_valid
        ):
            blockers.append(
                "AIRANK_COMPROMISED_CREDENTIALS_ROTATED must attest that every exposed credential was rotated"
            )
        elif quarantine_valid:
            warnings.append(
                "unrotated exposed Provider credentials are disabled and quarantined; release readiness remains blocked"
            )
        elif temporary_exception_valid:
            warnings.append(
                "unrotated exposed Provider credentials are temporarily enabled for experience testing; release readiness remains blocked"
            )

    configured = 0
    for provider in PROVIDER_NAMES:
        prefix = provider.upper()
        disabled = _enabled(source, f"{prefix}_PROVIDER_DISABLED")
        endpoint = _clean(source, f"{prefix}_API_URL")
        model = _clean(source, f"{prefix}_MODEL")
        key = _clean(source, f"{prefix}_API_KEY")
        if disabled:
            continue
        if endpoint and not _absolute_https(endpoint):
            blockers.append(f"{prefix}_API_URL must be an absolute HTTPS URL")
        if key and _is_placeholder(key):
            blockers.append(f"{prefix}_API_KEY contains placeholder material")
        if key and endpoint and model:
            configured += 1
    if mode == "api" and configured < 4:
        warnings.append(
            "fewer than four environment Provider routes are configured; release evidence must prove tenant-vault routes"
        )

    deepseek_disabled = _enabled(source, "DEEPSEEK_PROVIDER_DISABLED")
    deepseek_model = _clean(source, "DEEPSEEK_MODEL").lower()
    if not deepseek_disabled and deepseek_model == "deepseek-v3.2":
        blockers.append(
            "DEEPSEEK_MODEL=deepseek-v3.2 is inside the production migration window; "
            "validate and approve a non-sunsetting replacement before launch"
        )


def _validate_public_surface(source: Mapping[str, str], blockers: list[str]) -> None:
    public_origin = _clean(source, "AIRANK_PUBLIC_ORIGIN")
    if not _absolute_https(public_origin) or _is_placeholder(public_origin) or urlparse(public_origin).hostname in {
        "127.0.0.1",
        "localhost",
    }:
        blockers.append("AIRANK_PUBLIC_ORIGIN must be the final public HTTPS origin")
    build_commit = _clean(source, "AIRANK_BUILD_COMMIT").lower()
    if not COMMIT_RE.fullmatch(build_commit) or build_commit == "0" * 40:
        blockers.append("AIRANK_BUILD_COMMIT must be the immutable 40-character Git commit")
    allowed_hosts = [
        value.strip().lower()
        for value in _clean(source, "AIRANK_PUBLISH_ALLOWED_HOSTS").split(",")
        if value.strip()
    ]
    if not allowed_hosts or any(
        "://" in host
        or "/" in host
        or _is_placeholder(host)
        or host in {"localhost", "127.0.0.1"}
        for host in allowed_hosts
    ):
        blockers.append("AIRANK_PUBLISH_ALLOWED_HOSTS must contain exact production hostnames")
    if _clean(source, "AIRANK_WORDPRESS_POST_STATUS").lower() not in {"draft", "pending"}:
        blockers.append("AIRANK_WORDPRESS_POST_STATUS must default to draft or pending")


def _validate_optional_integrations(source: Mapping[str, str], blockers: list[str]) -> None:
    capability_mode = _clean(source, "XINGHE_CAPABILITY_MODE").lower()
    if capability_mode not in {"disabled", "adapter"}:
        blockers.append("XINGHE_CAPABILITY_MODE must be disabled or adapter")
    if capability_mode == "adapter":
        for name in (
            "XINGHE_CRAWLER_GATEWAY_BASE_URL",
            "XINGHE_KB_SERVICE_BASE_URL",
            "XINGHE_CREATOR_MARKETING_BASE_URL",
            "XINGHE_WORKFLOW_RUNNER_BASE_URL",
        ):
            value = _clean(source, name)
            if value and not _absolute_https(value):
                blockers.append(f"{name} must be HTTPS when configured")
    webhook = _clean(source, "AIRANK_REVIEW_NOTIFICATION_WEBHOOK_URL")
    if webhook and not _absolute_https(webhook):
        blockers.append("AIRANK_REVIEW_NOTIFICATION_WEBHOOK_URL must be HTTPS")


def validate_production_environment(
    env: Mapping[str, str] | None = None,
    *,
    role: str = "release",
) -> PreflightResult:
    source = os.environ if env is None else env
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    if _clean(source, "AIRANK_ENV").lower() != "production":
        blockers.append("AIRANK_ENV must be production")
    checks.append("runtime_mode")

    _validate_database(source, blockers)
    checks.append("database_transport")
    _validate_object_storage(source, blockers)
    checks.append("immutable_object_storage")
    _validate_single_node(source, blockers)
    checks.append("single_node_boundary")
    _validate_public_surface(source, blockers)
    checks.append("public_surface")

    # Schema migration consumes only deployment identity, database transport,
    # storage boundaries, and a verified backup receipt. Requiring API auth,
    # Provider credentials, or optional integrations here couples a reversible
    # database operation to unrelated application launch gates. Every process
    # that serves or executes customer work still validates the full runtime.
    if role != "migration":
        _validate_auth(source, blockers)
        checks.append("authentication_authority")

        _, encryption_keys = _key_map(
            source,
            active_name="AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID",
            mapping_name="AIRANK_CREDENTIAL_ENCRYPTION_KEYS",
            blockers=blockers,
        )
        _, fingerprint_keys = _key_map(
            source,
            active_name="AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID",
            mapping_name="AIRANK_CREDENTIAL_FINGERPRINT_KEYS",
            blockers=blockers,
        )
        if set(encryption_keys.values()) & set(fingerprint_keys.values()):
            blockers.append(
                "encryption and fingerprint keyrings must use distinct key material"
            )
        checks.append("provider_credential_keyrings")

        _validate_provider_runtime(source, blockers, warnings, role=role)
        checks.append("provider_execution")
        _validate_optional_integrations(source, blockers)
        checks.append("external_integrations")

    if role == "release":
        release_tenant_id = _clean(source, "AIRANK_RELEASE_TENANT_ID")
        release_yudao_tenant_id = _clean(
            source, "AIRANK_RELEASE_YUDAO_TENANT_ID"
        )
        if not release_tenant_id or release_tenant_id == "tenant_demo":
            blockers.append(
                "AIRANK_RELEASE_TENANT_ID must identify the real release tenant"
            )
        if not release_yudao_tenant_id:
            blockers.append(
                "AIRANK_RELEASE_YUDAO_TENANT_ID must identify the bound Yudao tenant"
            )
        checks.append("release_tenant_scope")

    if role == "worker":
        if not _enabled(source, "AIRANK_WORKER_GLOBAL_SCOPE_ENABLED"):
            blockers.append("AIRANK_WORKER_GLOBAL_SCOPE_ENABLED must be true for the production global worker")
        worker_id = _clean(source, "AIRANK_WORKER_ID")
        if not worker_id or worker_id.startswith("local-"):
            blockers.append("AIRANK_WORKER_ID must identify the production worker instance")
        checks.append("worker_scope")
    if role == "migration":
        backup_receipt = _clean(source, "AIRANK_DATABASE_BACKUP_RECEIPT")
        if (
            len(backup_receipt) < 8
            or len(backup_receipt) > 160
            or _is_placeholder(backup_receipt)
        ):
            blockers.append(
                "AIRANK_DATABASE_BACKUP_RECEIPT must identify a verified pre-migration backup"
            )
        checks.append("migration_backup_receipt")
    if role == "scheduler":
        if not _enabled(source, "AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED"):
            blockers.append(
                "AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED must be true for the production global scheduler"
            )
        scheduler_id = _clean(source, "AIRANK_SCHEDULER_ID")
        if not scheduler_id or scheduler_id.startswith("local-"):
            blockers.append("AIRANK_SCHEDULER_ID must identify the production scheduler instance")
        checks.append("scheduler_scope")

    return PreflightResult(
        role=role,
        checks=tuple(checks),
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AIRank production configuration without side effects")
    parser.add_argument(
        "--role",
        choices=("release", "migration", "api", "worker", "scheduler"),
        default="release",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = validate_production_environment(role=args.role)
    print(json.dumps(result.to_record(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
