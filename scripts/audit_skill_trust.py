#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "score" / "src",
    ROOT / "packages" / "skills" / "src",
):
    sys.path.insert(0, str(source_path))

from airank_skills import build_trust_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit AIRank internal Skill trust and isolated-install boundaries.")
    parser.add_argument("--report", type=Path, help="Optional JSON report output path.")
    parser.add_argument(
        "--skip-install-simulation",
        action="store_true",
        help="Run only declaration/source checks. A skipped install simulation never passes the full trust gate.",
    )
    args = parser.parse_args()
    report = build_trust_report(run_install_simulation=not args.skip_install_simulation)
    if args.report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "claim_level": report["claim_level"],
                "native_runtime_enforcement": report["native_runtime_enforcement"],
                **report["summary"],
                "report_sha256": report["report_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
