#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
for source_path in (
    ROOT / "packages" / "domain" / "src",
    ROOT / "packages" / "evidence" / "src",
):
    sys.path.insert(0, str(source_path))

from airank_evidence import (  # noqa: E402
    ReportEvidencePacketVerificationError,
    verify_report_evidence_packet,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an AIRank v7 customer evidence ZIP against the external "
            "content_sha256 returned by AIRank or its download receipt."
        )
    )
    parser.add_argument("packet", type=Path, help="Downloaded AIRank evidence ZIP.")
    parser.add_argument(
        "--expected-sha256",
        required=True,
        help="External SHA-256 anchor from AIRank API/download receipt.",
    )
    args = parser.parse_args()

    try:
        result = verify_report_evidence_packet(
            args.packet.read_bytes(),
            expected_sha256=args.expected_sha256,
        )
    except (OSError, ReportEvidencePacketVerificationError) as exc:
        print(
            json.dumps(
                {"status": "failed", "reason": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1

    print(json.dumps(result.to_record(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
