from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "production_preflight",
    ROOT / "scripts" / "production_preflight.py",
)
assert SPEC and SPEC.loader
production_preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = production_preflight
SPEC.loader.exec_module(production_preflight)

STORAGE_PROBE_SPEC = importlib.util.spec_from_file_location(
    "probe_object_storage",
    ROOT / "scripts" / "probe_object_storage.py",
)
assert STORAGE_PROBE_SPEC and STORAGE_PROBE_SPEC.loader
probe_object_storage = importlib.util.module_from_spec(STORAGE_PROBE_SPEC)
sys.modules[STORAGE_PROBE_SPEC.name] = probe_object_storage
STORAGE_PROBE_SPEC.loader.exec_module(probe_object_storage)

TENANT_BINDING_SPEC = importlib.util.spec_from_file_location(
    "check_tenant_binding",
    ROOT / "scripts" / "check_tenant_binding.py",
)
assert TENANT_BINDING_SPEC and TENANT_BINDING_SPEC.loader
check_tenant_binding = importlib.util.module_from_spec(TENANT_BINDING_SPEC)
sys.modules[TENANT_BINDING_SPEC.name] = check_tenant_binding
TENANT_BINDING_SPEC.loader.exec_module(check_tenant_binding)


def encoded(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode("ascii")


def production_env() -> dict[str, str]:
    return {
        "AIRANK_ENV": "production",
        "AIRANK_PUBLIC_ORIGIN": "https://console.airank.cn",
        "AIRANK_BUILD_COMMIT": "a" * 40,
        "AIRANK_RELEASE_TENANT_ID": "tenant_customer_a",
        "AIRANK_RELEASE_YUDAO_TENANT_ID": "1008",
        "AIRANK_DATABASE_URL": (
            "mysql+pymysql://airank:strong-secret@mysql.airank-db.cn:3306/airank_laike"
            "?charset=utf8mb4&ssl_ca=/run/secrets/mysql-ca.pem"
            "&ssl_verify_cert=true&ssl_verify_identity=true"
        ),
        "AIRANK_AUTH_MODE": "yudao",
        "AIRANK_API_AUTH_ENFORCEMENT": "required",
        "AIRANK_TENANT_RESOLUTION_MODE": "database",
        "AIRANK_PROVIDER_ADMIN_PERMISSION": "airank:provider:admin",
        "AIRANK_PROVIDER_PLATFORM_ADMIN_PERMISSION": "airank:provider:platform-admin",
        "YUDAO_BASE_URL": "https://yudao.airank.cn",
        "YUDAO_PERMISSION_INFO_URL": (
            "https://yudao.airank.cn/admin-api/system/auth/get-permission-info"
        ),
        "YUDAO_MODEL_RESOLVE_URL": (
            "https://yudao.airank.cn/admin-api/ai/model/resolve"
        ),
        "YUDAO_BEARER_TOKEN": "runtime-secret",
        "AIRANK_OBJECT_STORAGE_DRIVER": "s3",
        "AIRANK_S3_ENDPOINT_URL": "https://objects.airank.cn",
        "AIRANK_S3_BUCKET": "airank-production-evidence",
        "AIRANK_S3_ALLOW_HTTP": "false",
        "AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID": "enc-2026-08",
        "AIRANK_CREDENTIAL_ENCRYPTION_KEYS": json.dumps(
            {"enc-2026-08": encoded(1)}
        ),
        "AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID": "fp-2026-08",
        "AIRANK_CREDENTIAL_FINGERPRINT_KEYS": json.dumps(
            {"fp-2026-08": encoded(2)}
        ),
        "AIRANK_PROVIDER_MODE": "api",
        "AIRANK_SCAN_DISPATCH_MODE": "worker",
        "AIRANK_ALLOW_CUSTOM_PROVIDER_ENDPOINTS": "false",
        "AIRANK_COMPROMISED_CREDENTIALS_ROTATED": "true",
        "QIANWEN_API_URL": (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        ),
        "QIANWEN_MODEL": "qwen3.6-plus",
        "QIANWEN_API_KEY": "qianwen-runtime-secret",
        "DOUBAO_API_URL": "https://ark.cn-beijing.volces.com/api/v3/responses",
        "DOUBAO_MODEL": "doubao-seed-2-0-lite-260215",
        "DOUBAO_API_KEY": "doubao-runtime-secret",
        "KIMI_API_URL": "https://api.moonshot.cn/v1/chat/completions",
        "KIMI_MODEL": "kimi-k3",
        "KIMI_API_KEY": "rotated-kimi-runtime-secret",
        "DEEPSEEK_API_URL": (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        ),
        "DEEPSEEK_MODEL": "deepseek-v4-pro",
        "DEEPSEEK_API_KEY": "deepseek-runtime-secret",
        "AIRANK_PUBLISH_ALLOWED_HOSTS": "www.customer.cn",
        "AIRANK_WORDPRESS_POST_STATUS": "draft",
        "XINGHE_CAPABILITY_MODE": "disabled",
        "AIRANK_WORKER_GLOBAL_SCOPE_ENABLED": "true",
        "AIRANK_WORKER_ID": "airank-worker-production-1",
        "AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED": "true",
        "AIRANK_SCHEDULER_ID": "airank-scheduler-production-1",
    }


def test_production_preflight_accepts_a_hardened_api_environment() -> None:
    result = production_preflight.validate_production_environment(
        production_env(), role="api"
    )

    assert result.ready is True
    assert result.blockers == ()
    assert result.warnings == ()


def test_preflight_blocks_local_fallbacks_sunset_model_and_unrotated_secrets() -> None:
    env = production_env()
    env.update(
        {
            "AIRANK_ENV": "local",
            "AIRANK_PROVIDER_MODE": "mock",
            "AIRANK_DATABASE_URL": (
                "mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike"
            ),
            "AIRANK_OBJECT_STORAGE_DRIVER": "filesystem",
            "AIRANK_COMPROMISED_CREDENTIALS_ROTATED": "false",
            "DEEPSEEK_MODEL": "deepseek-v3.2",
            "AIRANK_TENANT_RESOLUTION_MODE": "default",
            "AIRANK_DEFAULT_TENANT_ID": "tenant_demo",
        }
    )

    result = production_preflight.validate_production_environment(env, role="api")

    assert result.ready is False
    detail = "\n".join(result.blockers)
    assert "AIRANK_ENV must be production" in detail
    assert "local or bundled development database" in detail
    assert "must be s3 or minio" in detail
    assert "mock/dev modes are forbidden" in detail
    assert "exposed credential was rotated" in detail
    assert "production migration window" in detail
    assert "TENANT_RESOLUTION_MODE must be database" in detail
    assert "DEFAULT_TENANT_ID must be unset" in detail


def test_preflight_rejects_key_reuse_across_cryptographic_domains() -> None:
    env = production_env()
    env["AIRANK_CREDENTIAL_FINGERPRINT_KEYS"] = env[
        "AIRANK_CREDENTIAL_ENCRYPTION_KEYS"
    ].replace("enc-2026-08", "fp-2026-08")

    result = production_preflight.validate_production_environment(env, role="api")

    assert result.ready is False
    assert any("distinct key material" in blocker for blocker in result.blockers)


def test_preflight_rejects_unsafe_object_storage_timeout() -> None:
    env = production_env()
    env["AIRANK_S3_TIMEOUT_SECONDS"] = "301"

    result = production_preflight.validate_production_environment(env, role="api")

    assert result.ready is False
    assert any("AIRANK_S3_TIMEOUT_SECONDS" in blocker for blocker in result.blockers)


def test_worker_and_scheduler_fail_closed_without_explicit_global_scope() -> None:
    env = production_env()
    env["AIRANK_WORKER_GLOBAL_SCOPE_ENABLED"] = "false"
    env["AIRANK_SCHEDULER_GLOBAL_SCOPE_ENABLED"] = "false"

    worker = production_preflight.validate_production_environment(env, role="worker")
    scheduler = production_preflight.validate_production_environment(
        env, role="scheduler"
    )

    assert worker.ready is False
    assert scheduler.ready is False
    assert any("WORKER_GLOBAL_SCOPE" in blocker for blocker in worker.blockers)
    assert any("SCHEDULER_GLOBAL_SCOPE" in blocker for blocker in scheduler.blockers)


def test_migration_requires_a_verified_backup_receipt() -> None:
    env = production_env()

    blocked = production_preflight.validate_production_environment(
        env, role="migration"
    )
    env["AIRANK_DATABASE_BACKUP_RECEIPT"] = "rds-snapshot-20260809-001"
    ready = production_preflight.validate_production_environment(env, role="migration")

    assert blocked.ready is False
    assert any("BACKUP_RECEIPT" in blocker for blocker in blocked.blockers)
    assert ready.ready is True


def test_preflight_public_record_never_contains_secret_values() -> None:
    env = production_env()
    result = production_preflight.validate_production_environment(env, role="api")
    rendered = json.dumps(result.to_record(), ensure_ascii=False)

    for name in (
        "YUDAO_BEARER_TOKEN",
        "QIANWEN_API_KEY",
        "DOUBAO_API_KEY",
        "KIMI_API_KEY",
        "DEEPSEEK_API_KEY",
    ):
        assert env[name] not in rendered


def test_production_deployment_bundle_is_immutable_and_has_distinct_processes() -> None:
    compose = (ROOT / "ops/deployment/compose.production.yml").read_text(
        encoding="utf-8"
    )
    backend = (ROOT / "ops/deployment/Dockerfile.backend").read_text(
        encoding="utf-8"
    )
    web = (ROOT / "ops/deployment/Dockerfile.web").read_text(encoding="utf-8")
    nginx = (ROOT / "ops/deployment/nginx-console.conf").read_text(
        encoding="utf-8"
    )

    for service in ("migrate:", "api:", "worker:", "scheduler:", "web:"):
        assert service in compose
    assert "service_completed_successfully" in compose
    assert "service_healthy" in compose
    assert compose.count("read_only: true") >= 2
    assert "no-new-privileges:true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose
    assert "pids_limit:" in compose
    assert "max-size: 20m" in compose
    assert "resources:" in compose and "memory:" in compose
    assert "USER 10001:10001" in backend
    assert "requirements-prod.lock" in backend
    assert "pip==26.2.1" in backend
    assert "setuptools==84.0.0" in backend
    assert "--no-access-log" in backend
    assert "--no-access-log" in compose
    assert "npm run build" in web
    assert "npm run check:bundle" in web
    assert backend.startswith("FROM python:3.11.15-slim-bookworm@sha256:")
    assert "FROM node:22.12.0-alpine@sha256:" in web
    assert "FROM nginxinc/nginx-unprivileged:1.30.4-alpine@sha256:" in web
    assert "vite preview" not in compose
    assert "Content-Security-Policy" in nginx
    assert "add_header_inherit merge" in nginx
    assert "server_tokens off" in nginx


def test_production_dependency_lock_uses_only_exact_versions() -> None:
    lock = (ROOT / "apps/api/requirements-prod.lock").read_text(encoding="utf-8")
    requirements = [
        line.strip()
        for line in lock.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert requirements
    assert all(
        re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", requirement)
        for requirement in requirements
    )


def test_release_preflight_requires_a_real_explicit_tenant_scope() -> None:
    env = production_env()
    env["AIRANK_RELEASE_TENANT_ID"] = "tenant_demo"
    env["AIRANK_RELEASE_YUDAO_TENANT_ID"] = ""

    result = production_preflight.validate_production_environment(
        env, role="release"
    )

    assert result.ready is False
    assert any("real release tenant" in blocker for blocker in result.blockers)
    assert any("bound Yudao tenant" in blocker for blocker in result.blockers)


def test_object_storage_probe_requires_explicit_release_authorization() -> None:
    code, record = probe_object_storage.run_probe(production_env())

    assert code == 1
    assert record["reason_code"] == "STORAGE_PROBE_NOT_AUTHORIZED"


def test_object_storage_probe_performs_real_idempotent_write_and_read(tmp_path) -> None:
    from airank_evidence import FilesystemObjectStorage

    env = production_env()
    env["AIRANK_RELEASE_RUN_STORAGE_PROBE"] = "true"
    storage = FilesystemObjectStorage(tmp_path / "objects")
    storage.driver = "s3"

    first_code, first = probe_object_storage.run_probe(
        env, storage_factory=lambda _env: storage
    )
    second_code, second = probe_object_storage.run_probe(
        env, storage_factory=lambda _env: storage
    )

    assert first_code == second_code == 0
    assert first == second
    assert first["status"] == "pass"
    assert first["driver"] == "s3"


def test_release_tenant_binding_requires_one_exact_active_mapping() -> None:
    valid = check_tenant_binding.evaluate_binding_rows(
        [
            {
                "tenant_id": "tenant_customer_a",
                "yudao_tenant_id": "1008",
                "status": "active",
            }
        ],
        expected_tenant_id="tenant_customer_a",
        expected_yudao_tenant_id="1008",
    )
    conflicting = check_tenant_binding.evaluate_binding_rows(
        [
            {
                "tenant_id": "tenant_customer_a",
                "yudao_tenant_id": "1008",
                "status": "active",
            },
            {
                "tenant_id": "tenant_customer_b",
                "yudao_tenant_id": "1009",
                "status": "active",
            },
        ],
        expected_tenant_id="tenant_customer_a",
        expected_yudao_tenant_id="1008",
    )
    inactive = check_tenant_binding.evaluate_binding_rows(
        [
            {
                "tenant_id": "tenant_customer_a",
                "yudao_tenant_id": "1008",
                "status": "disabled",
            }
        ],
        expected_tenant_id="tenant_customer_a",
        expected_yudao_tenant_id="1008",
    )

    assert valid == ()
    assert "expected exactly one" in conflicting[0]
    assert "not active" in inactive[0]
