#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    ROOT,
    ROOT / "packages" / "provider-gateway" / "src",
):
    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

from apps.api.provider_model_lifecycle import MySQLProviderModelLifecycle  # noqa: E402


def main() -> int:
    database_url = str(
        os.getenv("AIRANK_RELEASE_DATABASE_URL")
        or os.getenv("AIRANK_DATABASE_URL")
        or os.getenv("ALEMBIC_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()
    tenant_id = os.getenv("AIRANK_RELEASE_TENANT_ID", "").strip()
    if not database_url or not tenant_id or tenant_id == "tenant_demo":
        print(json.dumps({"tenant_id": tenant_id, "routes": [], "blockers": ["release database URL or real release tenant id is missing"]}))
        return 1
    try:
        records = MySQLProviderModelLifecycle(database_url).list_release_gates(tenant_id)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "tenant_id": tenant_id,
                    "routes": [],
                    "blockers": [f"lifecycle repository failed: {type(exc).__name__}: {exc}"],
                },
                ensure_ascii=False,
            )
        )
        return 1
    blockers = [
        (
            f"{record['provider']}/{record['route_id']} model={record['model']} "
            f"status={record['lifecycle_status']} days_to_sunset={record['days_to_sunset']} "
            f"migration={record.get('migration_status') or 'missing'}: {record['lifecycle_reason']}"
        )
        for record in records
        if record["release_gate_status"] == "blocked"
    ]
    if not records:
        blockers.append("no persisted enabled Provider routes were found")
    print(
        json.dumps(
            {"tenant_id": tenant_id, "routes": records, "blockers": blockers},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
