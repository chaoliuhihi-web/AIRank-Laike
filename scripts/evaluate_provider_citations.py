#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROVIDER_GATEWAY_SRC = ROOT / "packages" / "provider-gateway" / "src"
sys.path.insert(0, str(PROVIDER_GATEWAY_SRC))

from airank_provider_gateway.adapters import (  # noqa: E402
    NATIVE_CITATION_PARSER_VERSION,
    detect_web_search,
    extract_citations,
)


DEFAULT_FIXTURE = (
    ROOT
    / "packages"
    / "provider-gateway"
    / "tests"
    / "fixtures"
    / "provider_native_citations_v1.json"
)


def _citation_record(citation: Any) -> dict[str, Any]:
    return {
        "url": citation.url,
        "native_type": citation.native_type,
        "source_path": citation.source_path,
        "source_id": citation.source_id,
    }


def evaluate_fixture(path: Path = DEFAULT_FIXTURE) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "airank.provider-native-citation-benchmark.v1":
        raise ValueError("unsupported provider citation benchmark schema")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("provider citation benchmark cases are missing or out of bounds")

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("provider citation benchmark case must be an object")
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in seen_ids:
            raise ValueError("provider citation benchmark case ids must be unique")
        seen_ids.add(case_id)
        response = case.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"{case_id}: response must be an object")
        search_requested = case.get("search_requested")
        if not isinstance(search_requested, bool):
            raise ValueError(f"{case_id}: search_requested must be boolean")

        search_used, search_evidence = detect_web_search(
            response,
            search_requested,
        )
        citations = [_citation_record(item) for item in extract_citations(response)]
        failures: list[str] = []
        if search_used != case.get("expected_search_used"):
            failures.append("search_used")
        if search_evidence != case.get("expected_search_evidence"):
            failures.append("search_evidence")
        if citations != case.get("expected_citations"):
            failures.append("citations")
        results.append(
            {
                "case_id": case_id,
                "status": "pass" if not failures else "fail",
                "failed_fields": failures,
                "citation_count": len(citations),
            }
        )

    passed = sum(1 for item in results if item["status"] == "pass")
    return {
        "status": "pass" if passed == len(results) else "fail",
        "schema_version": payload["schema_version"],
        "parser_version": NATIVE_CITATION_PARSER_VERSION,
        "case_count": len(results),
        "passed_case_count": passed,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate AIRank Provider-native citation extraction fixtures."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Versioned benchmark fixture JSON.",
    )
    args = parser.parse_args()
    try:
        result = evaluate_fixture(args.fixture)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "failed", "reason": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
