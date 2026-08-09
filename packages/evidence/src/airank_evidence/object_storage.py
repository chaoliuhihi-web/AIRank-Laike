from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse
from uuid import uuid4


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
READINESS_OBJECT_KEY = "_airank/system/readiness/object-storage-v1.txt"
READINESS_OBJECT_PAYLOAD = b"AIRank object storage readiness probe v1\n"
DEFAULT_S3_TIMEOUT_SECONDS = 10.0
MAXIMUM_S3_TIMEOUT_SECONDS = 300.0


class ObjectStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    uri: str
    content_type: str
    byte_size: int
    sha256: str
    driver: str


class ObjectStorage(Protocol):
    driver: str

    def put_file(
        self,
        source_path: str | Path,
        *,
        key: str,
        content_type: str,
        expected_sha256: str | None = None,
    ) -> StoredObject: ...

    def put_bytes(self, payload: bytes, *, key: str, content_type: str) -> StoredObject: ...

    def get_bytes(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_key(key: str) -> str:
    normalized = str(PurePosixPath(key.strip()))
    path = PurePosixPath(normalized)
    if not key.strip() or path.is_absolute() or ".." in path.parts or "\\" in key:
        raise ObjectStorageError("object key must be a non-empty relative POSIX path")
    return normalized


def validate_expected_sha256(expected_sha256: str | None, actual_sha256: str) -> None:
    if expected_sha256 is None:
        return
    normalized = expected_sha256.strip().lower()
    if not SHA256_RE.fullmatch(normalized):
        raise ObjectStorageError("expected SHA-256 must be 64 lowercase hexadecimal characters")
    if normalized != actual_sha256:
        raise ObjectStorageError("object SHA-256 does not match expected evidence hash")


def parse_s3_timeout_seconds(source: Mapping[str, str]) -> float:
    raw_value = source.get("AIRANK_S3_TIMEOUT_SECONDS", str(DEFAULT_S3_TIMEOUT_SECONDS)).strip()
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ObjectStorageError("AIRANK_S3_TIMEOUT_SECONDS must be a number between 1 and 300") from exc
    if timeout < 1 or timeout > MAXIMUM_S3_TIMEOUT_SECONDS:
        raise ObjectStorageError("AIRANK_S3_TIMEOUT_SECONDS must be a number between 1 and 300")
    return timeout


def provision_object_storage_readiness(storage: ObjectStorage) -> StoredObject:
    stored = storage.put_bytes(
        READINESS_OBJECT_PAYLOAD,
        key=READINESS_OBJECT_KEY,
        content_type="text/plain",
    )
    if storage.get_bytes(READINESS_OBJECT_KEY) != READINESS_OBJECT_PAYLOAD:
        raise ObjectStorageError("object storage readiness write-read verification failed")
    return stored


def verify_object_storage_readiness(storage: ObjectStorage) -> None:
    if storage.get_bytes(READINESS_OBJECT_KEY) != READINESS_OBJECT_PAYLOAD:
        raise ObjectStorageError("object storage readiness sentinel verification failed")


class FilesystemObjectStorage:
    driver = "filesystem"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def put_file(
        self,
        source_path: str | Path,
        *,
        key: str,
        content_type: str,
        expected_sha256: str | None = None,
    ) -> StoredObject:
        source = Path(source_path)
        if not source.is_file():
            raise ObjectStorageError(f"evidence source file does not exist: {source}")
        actual_sha256 = sha256_file(source)
        validate_expected_sha256(expected_sha256, actual_sha256)
        normalized_key = validate_key(key)
        target = self._target(normalized_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or sha256_file(target) != actual_sha256:
                raise ObjectStorageError("content-addressed object collision detected")
        else:
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                shutil.copyfile(source, temporary)
                if sha256_file(temporary) != actual_sha256:
                    raise ObjectStorageError("object copy verification failed")
                os.replace(temporary, target)
                target.chmod(0o444)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return self._stored(normalized_key, target, content_type, actual_sha256)

    def put_bytes(self, payload: bytes, *, key: str, content_type: str) -> StoredObject:
        normalized_key = validate_key(key)
        target = self._target(normalized_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        actual_sha256 = sha256_bytes(payload)
        if target.exists():
            if not target.is_file() or sha256_file(target) != actual_sha256:
                raise ObjectStorageError("content-addressed object collision detected")
        else:
            temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_bytes(payload)
                if sha256_file(temporary) != actual_sha256:
                    raise ObjectStorageError("object write verification failed")
                os.replace(temporary, target)
                target.chmod(0o444)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return self._stored(normalized_key, target, content_type, actual_sha256)

    def get_bytes(self, key: str) -> bytes:
        target = self._target(validate_key(key))
        if not target.is_file():
            raise ObjectStorageError("stored object does not exist")
        return target.read_bytes()

    def delete(self, key: str) -> None:
        target = self._target(validate_key(key))
        if target.exists():
            target.unlink()

    def _target(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root != target and self.root not in target.parents:
            raise ObjectStorageError("object key escapes configured storage root")
        return target

    def _stored(self, key: str, target: Path, content_type: str, sha256: str) -> StoredObject:
        return StoredObject(
            key=key,
            uri=target.as_uri(),
            content_type=content_type,
            byte_size=target.stat().st_size,
            sha256=sha256,
            driver=self.driver,
        )


class S3CompatibleObjectStorage:
    driver = "s3"

    def __init__(self, *, client: Any, bucket: str) -> None:
        if not BUCKET_RE.fullmatch(bucket):
            raise ObjectStorageError("invalid S3 bucket name")
        self.client = client
        self.bucket = bucket

    def put_file(
        self,
        source_path: str | Path,
        *,
        key: str,
        content_type: str,
        expected_sha256: str | None = None,
    ) -> StoredObject:
        source = Path(source_path)
        if not source.is_file():
            raise ObjectStorageError(f"evidence source file does not exist: {source}")
        payload_sha256 = sha256_file(source)
        validate_expected_sha256(expected_sha256, payload_sha256)
        normalized_key = validate_key(key)
        byte_size = source.stat().st_size
        if not self._already_stored(normalized_key, payload_sha256, byte_size):
            try:
                with source.open("rb") as handle:
                    self.client.put_object(
                        Bucket=self.bucket,
                        Key=normalized_key,
                        Body=handle,
                        ContentType=content_type,
                        Metadata={"sha256": payload_sha256, "immutable": "true"},
                    )
            except Exception as exc:
                raise ObjectStorageError(f"S3 upload failed: {type(exc).__name__}") from exc
            self._verify_head(normalized_key, payload_sha256, byte_size)
        return self._stored(normalized_key, content_type, byte_size, payload_sha256)

    def put_bytes(self, payload: bytes, *, key: str, content_type: str) -> StoredObject:
        normalized_key = validate_key(key)
        payload_sha256 = sha256_bytes(payload)
        if not self._already_stored(normalized_key, payload_sha256, len(payload)):
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=normalized_key,
                    Body=payload,
                    ContentType=content_type,
                    Metadata={"sha256": payload_sha256, "immutable": "true"},
                )
            except Exception as exc:
                raise ObjectStorageError(f"S3 upload failed: {type(exc).__name__}") from exc
            self._verify_head(normalized_key, payload_sha256, len(payload))
        return self._stored(normalized_key, content_type, len(payload), payload_sha256)

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=validate_key(key))
            body = response["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)
        except ObjectStorageError:
            raise
        except Exception as exc:
            raise ObjectStorageError(f"S3 download failed: {type(exc).__name__}") from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))
        except ObjectStorageError:
            raise
        except Exception as exc:
            raise ObjectStorageError(f"S3 delete failed: {type(exc).__name__}") from exc

    def _stored(self, key: str, content_type: str, byte_size: int, sha256: str) -> StoredObject:
        return StoredObject(
            key=key,
            uri=f"s3://{self.bucket}/{key}",
            content_type=content_type,
            byte_size=byte_size,
            sha256=sha256,
            driver=self.driver,
        )

    def _head(self, key: str) -> Mapping[str, Any] | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str((response.get("Error") or {}).get("Code") or "") if isinstance(response, Mapping) else ""
            if code in {"404", "NoSuchKey", "NotFound"} or type(exc).__name__ in {"NoSuchKey", "NotFound"}:
                return None
            raise ObjectStorageError(f"S3 head failed: {type(exc).__name__}") from exc

    def _already_stored(self, key: str, sha256: str, byte_size: int) -> bool:
        head = self._head(key)
        if head is None:
            return False
        metadata = head.get("Metadata") or {}
        if int(head.get("ContentLength") or -1) == byte_size and metadata.get("sha256") == sha256:
            return True
        raise ObjectStorageError("content-addressed S3 object collision detected")

    def _verify_head(self, key: str, sha256: str, byte_size: int) -> None:
        head = self._head(key)
        if head is None:
            raise ObjectStorageError("S3 object is missing after upload")
        metadata = head.get("Metadata") or {}
        if int(head.get("ContentLength") or -1) != byte_size or metadata.get("sha256") != sha256:
            raise ObjectStorageError("S3 object metadata verification failed")


def build_object_storage_from_env(
    env: Mapping[str, str] | None = None,
    *,
    s3_client: Any | None = None,
) -> ObjectStorage:
    source = os.environ if env is None else env
    driver = source.get("AIRANK_OBJECT_STORAGE_DRIVER", "local").strip().lower()
    if driver in {"local", "filesystem"}:
        root = source.get("AIRANK_OBJECT_STORAGE_ROOT", ".runtime/objects").strip()
        if not root:
            raise ObjectStorageError("AIRANK_OBJECT_STORAGE_ROOT is required")
        return FilesystemObjectStorage(root)
    if driver not in {"s3", "minio"}:
        raise ObjectStorageError(f"unsupported object storage driver: {driver}")

    endpoint = source.get("AIRANK_S3_ENDPOINT_URL", "").strip() or None
    if endpoint:
        parsed = urlparse(endpoint)
        allow_http = source.get("AIRANK_S3_ALLOW_HTTP", "false").strip().lower() in {"1", "true", "yes", "on"}
        if parsed.scheme not in ({"http", "https"} if allow_http else {"https"}) or not parsed.netloc:
            raise ObjectStorageError("S3 endpoint must be an absolute HTTPS URL unless AIRANK_S3_ALLOW_HTTP=true")
    bucket = source.get("AIRANK_S3_BUCKET", "").strip()
    if not bucket:
        raise ObjectStorageError("AIRANK_S3_BUCKET is required")
    if s3_client is None:
        try:
            import boto3  # type: ignore[import-not-found]
            from botocore.config import Config  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise ObjectStorageError("boto3 is required for S3-compatible object storage") from exc
        access_key = source.get("AIRANK_S3_ACCESS_KEY_ID", "").strip() or None
        secret_key = source.get("AIRANK_S3_SECRET_ACCESS_KEY", "").strip() or None
        if bool(access_key) != bool(secret_key):
            raise ObjectStorageError("both S3 access key and secret key must be configured together")
        timeout_seconds = parse_s3_timeout_seconds(source)
        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            region_name=source.get("AIRANK_S3_REGION", "us-east-1").strip() or "us-east-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=source.get("AIRANK_S3_SESSION_TOKEN", "").strip() or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": source.get("AIRANK_S3_ADDRESSING_STYLE", "path")},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=timeout_seconds,
                read_timeout=timeout_seconds,
            ),
        )
    return S3CompatibleObjectStorage(client=s3_client, bucket=bucket)
