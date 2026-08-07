#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for source_path in (ROOT / "packages" / "domain" / "src", ROOT / "packages" / "skills" / "src"):
    sys.path.insert(0, str(source_path))

from airank_skills import build_promotion_ledger, evaluate_registry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate AIRank core Skills and build promotion evidence ledger.")
    parser.add_argument("--report", type=Path, help="Optional JSON ledger output path.")
    parser.add_argument(
        "--require-promotion-eligible",
        action="store_true",
        help="Fail unless every Skill has all external promotion evidence. Local CI normally omits this.",
    )
    args = parser.parse_args()
    reports = evaluate_registry()
    ledger = build_promotion_ledger()
    if args.report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "status": "pass" if all(report.local_eval_status == "passed" for report in reports) else "failed",
        "skill_count": len(reports),
        "case_count": sum(report.total_cases for report in reports),
        "passed_case_count": sum(report.passed_cases for report in reports),
        "promotion_eligible_count": sum(report.promotion_eligible for report in reports),
        "retained_partial_count": sum(not report.promotion_eligible for report in reports),
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if summary["status"] != "pass":
        return 1
    if args.require_promotion_eligible and summary["promotion_eligible_count"] != summary["skill_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
