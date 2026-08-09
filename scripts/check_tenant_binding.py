#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from typing import Any, Mapping, Sequence

from sqlalchemy import create_engine, text


TENANT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def evaluate_binding_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_tenant_id: str,
    expected_yudao_tenant_id: str,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if len(rows) != 1:
        blockers.append("expected exactly one active tenant binding")
        return tuple(blockers)
    row = rows[0]
    if str(row.get("tenant_id") or "") != expected_tenant_id:
        blockers.append("AIRank tenant id does not match the release tenant")
    if str(row.get("yudao_tenant_id") or "") != expected_yudao_tenant_id:
        blockers.append("Yudao tenant id does not match the release tenant binding")
    if str(row.get("status") or "") != "active":
        blockers.append("release tenant binding is not active")
    return tuple(blockers)


def main() -> int:
    database_url = str(
        os.getenv("AIRANK_RELEASE_DATABASE_URL")
        or os.getenv("AIRANK_DATABASE_URL")
        or ""
    ).strip()
    tenant_id = str(os.getenv("AIRANK_RELEASE_TENANT_ID") or "").strip()
    yudao_tenant_id = str(
        os.getenv("AIRANK_RELEASE_YUDAO_TENANT_ID") or ""
    ).strip()
    if (
        not database_url
        or not TENANT_ID_RE.fullmatch(tenant_id)
        or tenant_id == "tenant_demo"
        or not TENANT_ID_RE.fullmatch(yudao_tenant_id)
    ):
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason_code": "TENANT_BINDING_INPUT_INVALID",
                },
                sort_keys=True,
            )
        )
        return 1
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT tenant_id, yudao_tenant_id, status
                    FROM airank_tenant_bindings
                    WHERE deleted_at IS NULL
                      AND (tenant_id=:tenant_id OR yudao_tenant_id=:yudao_tenant_id)
                    """
                ),
                {"tenant_id": tenant_id, "yudao_tenant_id": yudao_tenant_id},
            ).mappings().all()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason_code": "TENANT_BINDING_QUERY_FAILED",
                    "error_type": type(exc).__name__,
                },
                sort_keys=True,
            )
        )
        return 1
    blockers = evaluate_binding_rows(
        rows,
        expected_tenant_id=tenant_id,
        expected_yudao_tenant_id=yudao_tenant_id,
    )
    print(
        json.dumps(
            {
                "status": "blocked" if blockers else "pass",
                "tenant_id": tenant_id,
                "yudao_tenant_id": yudao_tenant_id,
                "blockers": blockers,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
