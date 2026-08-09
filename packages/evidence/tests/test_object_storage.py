from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from airank_evidence import (
    FilesystemObjectStorage,
    ObjectStorageError,
    READINESS_OBJECT_KEY,
    S3CompatibleObjectStorage,
    build_object_storage_from_env,
    provision_object_storage_readiness,
    verify_object_storage_readiness,
)


class FakeNotFound(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.put_count = 0

    def head_object(self, *, Bucket: str, Key: str):
        try:
            item = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise FakeNotFound() from exc
        return {"ContentLength": len(item["body"]), "Metadata": item["metadata"]}

    def put_object(self, *, Bucket: str, Key: str, Body, ContentType: str, Metadata: dict[str, str]):
        payload = Body.read() if hasattr(Body, "read") else bytes(Body)
        self.objects[(Bucket, Key)] = {
            "body": payload,
            "content_type": ContentType,
            "metadata": dict(Metadata),
        }
        self.put_count += 1

    def get_object(self, *, Bucket: str, Key: str):
        return {"Body": BytesIO(self.objects[(Bucket, Key)]["body"])}

    def delete_object(self, *, Bucket: str, Key: str):
        self.objects.pop((Bucket, Key), None)


def test_filesystem_storage_is_content_addressed_and_verified(tmp_path: Path) -> None:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    source = tmp_path / "capture.png"
    source.write_bytes(b"immutable-evidence")
    expected_sha256 = "6da17499ca0ebd2dd4cfb96bcfc0dcf69e30e38658d3f5926bac537308ece100"

    stored = storage.put_file(
        source,
        key=f"evidence/{expected_sha256}.png",
        content_type="image/png",
        expected_sha256=expected_sha256,
    )
    replay = storage.put_file(
        source,
        key=f"evidence/{expected_sha256}.png",
        content_type="image/png",
        expected_sha256=expected_sha256,
    )

    assert stored == replay
    assert stored.uri.startswith("file://")
    assert stored.byte_size == len(b"immutable-evidence")
    assert storage.get_bytes(stored.key) == b"immutable-evidence"
    with pytest.raises(ObjectStorageError, match="does not match"):
        storage.put_file(
            source,
            key="evidence/wrong.png",
            content_type="image/png",
            expected_sha256="0" * 64,
        )
    with pytest.raises(ObjectStorageError, match="relative POSIX"):
        storage.put_bytes(b"escape", key="../escape", content_type="text/plain")


def test_s3_storage_is_idempotent_and_rejects_key_collisions() -> None:
    client = FakeS3Client()
    storage = S3CompatibleObjectStorage(client=client, bucket="airank-evidence")

    first = storage.put_bytes(b"evidence-one", key="evidence/one.bin", content_type="application/octet-stream")
    replay = storage.put_bytes(b"evidence-one", key="evidence/one.bin", content_type="application/octet-stream")

    assert first == replay
    assert first.uri == "s3://airank-evidence/evidence/one.bin"
    assert client.put_count == 1
    assert storage.get_bytes(first.key) == b"evidence-one"
    with pytest.raises(ObjectStorageError, match="collision"):
        storage.put_bytes(b"different", key="evidence/one.bin", content_type="application/octet-stream")
    storage.delete(first.key)
    assert client.objects == {}


def test_storage_readiness_sentinel_is_idempotent_and_verified() -> None:
    client = FakeS3Client()
    storage = S3CompatibleObjectStorage(client=client, bucket="airank-evidence")

    first = provision_object_storage_readiness(storage)
    second = provision_object_storage_readiness(storage)
    verify_object_storage_readiness(storage)

    assert first == second
    assert first.key == READINESS_OBJECT_KEY
    assert client.put_count == 1

    client.objects[("airank-evidence", READINESS_OBJECT_KEY)]["body"] = b"tampered"
    with pytest.raises(ObjectStorageError, match="sentinel verification failed"):
        verify_object_storage_readiness(storage)


def test_s3_factory_requires_https_unless_http_is_explicitly_allowed() -> None:
    client = FakeS3Client()
    base_env = {
        "AIRANK_OBJECT_STORAGE_DRIVER": "s3",
        "AIRANK_S3_BUCKET": "airank-evidence",
        "AIRANK_S3_ENDPOINT_URL": "http://minio.local:9000",
    }

    with pytest.raises(ObjectStorageError, match="HTTPS"):
        build_object_storage_from_env(base_env, s3_client=client)

    storage = build_object_storage_from_env(
        {**base_env, "AIRANK_S3_ALLOW_HTTP": "true"},
        s3_client=client,
    )
    assert isinstance(storage, S3CompatibleObjectStorage)


def test_s3_factory_applies_bounded_network_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    import boto3

    captured: dict[str, object] = {}

    def fake_client(service_name: str, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return FakeS3Client()

    monkeypatch.setattr(boto3, "client", fake_client)
    storage = build_object_storage_from_env(
        {
            "AIRANK_OBJECT_STORAGE_DRIVER": "s3",
            "AIRANK_S3_BUCKET": "airank-evidence",
            "AIRANK_S3_ENDPOINT_URL": "https://objects.example.com",
            "AIRANK_S3_TIMEOUT_SECONDS": "7.5",
        }
    )

    assert isinstance(storage, S3CompatibleObjectStorage)
    assert captured["service_name"] == "s3"
    config = captured["config"]
    assert config.connect_timeout == 7.5
    assert config.read_timeout == 7.5


@pytest.mark.parametrize("timeout", ["0", "301", "not-a-number"])
def test_s3_factory_rejects_unsafe_network_timeouts(monkeypatch: pytest.MonkeyPatch, timeout: str) -> None:
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeS3Client())

    with pytest.raises(ObjectStorageError, match="AIRANK_S3_TIMEOUT_SECONDS"):
        build_object_storage_from_env(
            {
                "AIRANK_OBJECT_STORAGE_DRIVER": "s3",
                "AIRANK_S3_BUCKET": "airank-evidence",
                "AIRANK_S3_ENDPOINT_URL": "https://objects.example.com",
                "AIRANK_S3_TIMEOUT_SECONDS": timeout,
            }
        )


@pytest.mark.parametrize("operation", ["put", "get", "delete"])
def test_s3_storage_sanitizes_client_failures(operation: str) -> None:
    class BrokenS3Client(FakeS3Client):
        def put_object(self, **kwargs):
            raise RuntimeError("https://access-key:secret-key@private-storage.example")

        def get_object(self, **kwargs):
            raise RuntimeError("https://access-key:secret-key@private-storage.example")

        def delete_object(self, **kwargs):
            raise RuntimeError("https://access-key:secret-key@private-storage.example")

    storage = S3CompatibleObjectStorage(client=BrokenS3Client(), bucket="airank-evidence")

    with pytest.raises(ObjectStorageError) as exc_info:
        if operation == "put":
            storage.put_bytes(b"payload", key="evidence/failure.bin", content_type="application/octet-stream")
        elif operation == "get":
            storage.get_bytes("evidence/failure.bin")
        else:
            storage.delete("evidence/failure.bin")

    assert "secret-key" not in str(exc_info.value)
    assert "private-storage.example" not in str(exc_info.value)
