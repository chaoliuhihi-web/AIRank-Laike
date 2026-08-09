#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_SOURCE = ROOT / "packages" / "domain" / "src"
EVIDENCE_SOURCE = ROOT / "packages" / "evidence" / "src"
for source_path in (DOMAIN_SOURCE, EVIDENCE_SOURCE):
    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

from airank_evidence import (  # noqa: E402
    ObjectStorage,
    ObjectStorageError,
    build_object_storage_from_env,
    provision_object_storage_readiness,
)


def enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def run_probe(
    env: Mapping[str, str],
    *,
    storage_factory: Callable[[Mapping[str, str]], ObjectStorage] = build_object_storage_from_env,
) -> tuple[int, dict[str, object]]:
    if not enabled(env.get("AIRANK_RELEASE_RUN_STORAGE_PROBE")):
        return 1, {
            "status": "blocked",
            "reason_code": "STORAGE_PROBE_NOT_AUTHORIZED",
            "detail": "set AIRANK_RELEASE_RUN_STORAGE_PROBE=true for the release environment",
        }
    if str(env.get("AIRANK_ENV") or "").strip().lower() != "production":
        return 1, {
            "status": "blocked",
            "reason_code": "NON_PRODUCTION_ENVIRONMENT",
        }
    try:
        storage = storage_factory(env)
        if storage.driver != "s3":
            raise ObjectStorageError("production probe requires the s3 storage driver")
        stored = provision_object_storage_readiness(storage)
    except ObjectStorageError as exc:
        return 1, {
            "status": "blocked",
            "reason_code": "STORAGE_WRITE_READ_FAILED",
            "error_type": type(exc).__name__,
        }
    return 0, {
        "status": "pass",
        "driver": stored.driver,
        "object_key": stored.key,
        "byte_size": stored.byte_size,
        "sha256": stored.sha256,
    }


def main() -> int:
    code, record = run_probe(os.environ)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
