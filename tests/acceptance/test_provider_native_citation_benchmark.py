from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_provider_native_citation_benchmark_is_versioned_and_passes() -> None:
    fixture = (
        ROOT
        / "packages"
        / "provider-gateway"
        / "tests"
        / "fixtures"
        / "provider_native_citations_v1.json"
    )
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "airank.provider-native-citation-benchmark.v1"
    assert len(payload["cases"]) >= 7
    assert any(
        case["case_id"] == "unrelated_urls_are_not_citations"
        and case["expected_citations"] == []
        for case in payload["cases"]
    )

    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_provider_citations.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "pass"
    assert result["case_count"] == result["passed_case_count"]
    assert result["parser_version"] == "airank.provider-native-citation.v2"


def test_release_gate_runs_provider_native_citation_benchmark() -> None:
    source = (ROOT / "scripts" / "release_readiness.py").read_text(encoding="utf-8")

    assert "provider citation benchmark" in source
    assert "scripts/evaluate_provider_citations.py" in source


def test_evidence_ui_exposes_request_kind_and_bounds_initial_citation_rendering() -> None:
    source = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(
        encoding="utf-8"
    )

    assert "EVIDENCE_CITATION_INITIAL_LIMIT = 20" in source
    assert "selected.citations.slice(0, EVIDENCE_CITATION_INITIAL_LIMIT)" in source
    assert "展开全部" in source
    assert "请求类型" in source
    assert "selectedRequestKind" in source
