#!/usr/bin/env python3
"""Create and version the configured S3 bucket without printing credentials."""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Mapping, Sequence


TRUE_VALUES = {"1", "true", "yes", "on"}


def enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in TRUE_VALUES


def build_client(env: Mapping[str, str]) -> Any:
    import boto3
    from botocore.config import Config

    timeout = float(env.get("AIRANK_S3_TIMEOUT_SECONDS", "10"))
    return boto3.client(
        "s3",
        endpoint_url=env.get("AIRANK_S3_ENDPOINT_URL") or None,
        region_name=env.get("AIRANK_S3_REGION", "us-east-1"),
        aws_access_key_id=env.get("AIRANK_S3_ACCESS_KEY_ID") or None,
        aws_secret_access_key=env.get("AIRANK_S3_SECRET_ACCESS_KEY") or None,
        aws_session_token=env.get("AIRANK_S3_SESSION_TOKEN") or None,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": env.get("AIRANK_S3_ADDRESSING_STYLE", "path")},
            retries={"max_attempts": 1, "mode": "standard"},
            connect_timeout=timeout,
            read_timeout=timeout,
        ),
    )


def is_missing_bucket(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    metadata = response.get("ResponseMetadata")
    code = str(error.get("Code") if isinstance(error, dict) else "")
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, dict) else None
    return code in {"404", "NoSuchBucket", "NotFound"} or status == 404


def provision_bucket(client: Any, *, bucket: str, region: str) -> dict[str, object]:
    created = False
    try:
        client.head_bucket(Bucket=bucket)
    except Exception as exc:
        if not is_missing_bucket(exc):
            raise
        request: dict[str, object] = {"Bucket": bucket}
        if region and region != "us-east-1":
            request["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**request)
        created = True
    client.put_bucket_versioning(
        Bucket=bucket,
        VersioningConfiguration={"Status": "Enabled"},
    )
    versioning = client.get_bucket_versioning(Bucket=bucket)
    if versioning.get("Status") != "Enabled":
        raise RuntimeError("bucket versioning was not enabled")
    return {"status": "pass", "bucket": bucket, "created": created, "versioning": "Enabled"}


def run(
    env: Mapping[str, str],
    *,
    wait_seconds: float,
    client_factory: Any = build_client,
) -> tuple[int, dict[str, object]]:
    if not enabled(env.get("AIRANK_OBJECT_STORAGE_BOOTSTRAP_ALLOWED")):
        return 1, {"status": "blocked", "reason_code": "OBJECT_STORAGE_BOOTSTRAP_NOT_AUTHORIZED"}
    bucket = str(env.get("AIRANK_S3_BUCKET") or "").strip()
    if not bucket:
        return 1, {"status": "blocked", "reason_code": "OBJECT_STORAGE_BUCKET_MISSING"}
    deadline = time.monotonic() + max(wait_seconds, 0)
    while True:
        try:
            client = client_factory(env)
            return 0, provision_bucket(
                client,
                bucket=bucket,
                region=str(env.get("AIRANK_S3_REGION") or "us-east-1").strip(),
            )
        except Exception:
            if time.monotonic() >= deadline:
                return 1, {"status": "blocked", "reason_code": "OBJECT_STORAGE_BOOTSTRAP_FAILED"}
            time.sleep(min(2.0, max(deadline - time.monotonic(), 0)))


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=float, default=0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(list(argv or [])) if argv is not None else parse_args(os.sys.argv[1:])
    code, record = run(os.environ, wait_seconds=args.wait_seconds)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
