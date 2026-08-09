from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography import x509


ROOT = Path(__file__).resolve().parents[2]


def load_bootstrap_module() -> Any:
    path = ROOT / "scripts" / "bootstrap_object_storage.py"
    spec = importlib.util.spec_from_file_location("bootstrap_object_storage", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_pki_module() -> Any:
    path = ROOT / "scripts" / "bootstrap_single_node_pki.py"
    spec = importlib.util.spec_from_file_location("bootstrap_single_node_pki", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MissingBucketError(RuntimeError):
    response = {
        "Error": {"Code": "NoSuchBucket"},
        "ResponseMetadata": {"HTTPStatusCode": 404},
    }


class FakeS3Client:
    def __init__(self) -> None:
        self.created = False
        self.versioning: dict[str, str] = {}

    def head_bucket(self, *, Bucket: str) -> None:
        del Bucket
        if not self.created:
            raise MissingBucketError()

    def create_bucket(self, **request: object) -> None:
        assert request["Bucket"] == "airank-production-evidence"
        self.created = True

    def put_bucket_versioning(
        self,
        *,
        Bucket: str,
        VersioningConfiguration: dict[str, str],
    ) -> None:
        del Bucket
        self.versioning = VersioningConfiguration

    def get_bucket_versioning(self, *, Bucket: str) -> dict[str, str]:
        del Bucket
        return self.versioning


def test_single_node_compose_keeps_state_on_the_data_disk() -> None:
    text = (ROOT / "ops" / "deployment" / "compose.single-node.production.yml").read_text()
    assert "${AIRANK_DATA_ROOT:?set AIRANK_DATA_ROOT}/mysql:/var/lib/mysql" in text
    assert "${AIRANK_DATA_ROOT:?set AIRANK_DATA_ROOT}/minio:/data" in text
    assert 'memory: 1536m' in text
    assert '127.0.0.1:${AIRANK_WEB_PORT:-18080}:8080' in text
    assert "--workers 1" in text
    assert "AIRANK_BACKEND_IMAGE" in text
    assert "AIRANK_WEB_IMAGE" in text
    assert "AIRANK_MYSQL_IMAGE" in text
    assert "AIRANK_MINIO_IMAGE" in text
    assert "AIRANK_NGINX_IMAGE" in text
    assert "--ssl-ca=/etc/mysql/certs/ca.pem" in text
    assert "--ssl-mode=REQUIRED" in text
    assert "service_started" in text
    assert "mc\n        - ready" not in text
    assert "host.docker.internal:host-gateway" in text
    assert "egress:" in text

    bootstrap = (ROOT / "ops" / "deployment" / "mysql" / "airank-init.sh").read_text()
    assert "eval " not in bootstrap
    assert "REQUIRE SSL" in bootstrap


def test_single_node_yudao_proxy_is_internal_tls_only() -> None:
    text = (ROOT / "ops" / "deployment" / "yudao-proxy.conf").read_text()

    assert "listen 8443 ssl" in text
    assert "proxy_pass http://host.docker.internal:48084" in text
    assert "ssl_protocols TLSv1.2 TLSv1.3" in text
    assert "listen 80" not in text

    relay = (
        ROOT
        / "ops"
        / "deployment"
        / "airank-yudao-loopback-relay.service"
    ).read_text()
    assert "bind=172.17.0.1" in relay
    assert "TCP4:127.0.0.1:48082" in relay
    assert "User=nobody" in relay
    assert "NoNewPrivileges=true" in relay
    assert "0.0.0.0" not in relay


def test_single_node_environment_template_fails_closed() -> None:
    text = (
        ROOT / "ops" / "deployment" / "env.single-node.production.example"
    ).read_text()

    assert "AIRANK_SINGLE_NODE_MODE=true" in text
    assert "AIRANK_DATA_ROOT=/home/www1/airank/data" in text
    assert "AIRANK_COMPROMISED_CREDENTIALS_ROTATED=false" in text
    assert "KIMI_PROVIDER_DISABLED=true" in text
    assert "DEEPSEEK_PROVIDER_DISABLED=true" in text
    assert "sk-" not in text


def test_single_node_pki_has_exact_service_dns_names_and_never_overwrites(
    tmp_path: Path,
) -> None:
    module = load_pki_module()
    output = tmp_path / "pki"
    record = module.provision_pki(
        output,
        now=datetime(2026, 8, 9, tzinfo=timezone.utc),
    )

    assert record["status"] == "pass"
    expected = {
        "mysql-server.pem": {"airank-db", "mysql"},
        "minio-public.crt": {"airank-objects", "minio"},
        "yudao-proxy.crt": {"airank-yudao", "yudao-proxy"},
    }
    for filename, dns_names in expected.items():
        certificate = x509.load_pem_x509_certificate((output / filename).read_bytes())
        extension = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        assert set(extension.value.get_values_for_type(x509.DNSName)) == dns_names
    assert (output / "ca-key.pem").stat().st_mode & 0o777 == 0o600
    assert (output / "manifest.json").stat().st_mode & 0o777 == 0o644

    try:
        module.provision_pki(output)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing PKI must never be overwritten")


def test_object_storage_bootstrap_requires_explicit_authorization() -> None:
    module = load_bootstrap_module()
    code, record = module.run({}, wait_seconds=0)
    assert code == 1
    assert record["reason_code"] == "OBJECT_STORAGE_BOOTSTRAP_NOT_AUTHORIZED"


def test_object_storage_bootstrap_creates_and_versions_bucket() -> None:
    module = load_bootstrap_module()
    client = FakeS3Client()
    code, record = module.run(
        {
            "AIRANK_OBJECT_STORAGE_BOOTSTRAP_ALLOWED": "true",
            "AIRANK_S3_BUCKET": "airank-production-evidence",
            "AIRANK_S3_REGION": "us-east-1",
        },
        wait_seconds=0,
        client_factory=lambda env: client,
    )
    assert code == 0
    assert record == {
        "status": "pass",
        "bucket": "airank-production-evidence",
        "created": True,
        "versioning": "Enabled",
    }
