from __future__ import annotations

from dataclasses import replace

from airank_skills import build_trust_report, load_default_registry
from airank_skills.trust import audit_manifest, inspect_runner_capabilities, trust_allows_skill


def test_every_core_skill_passes_repository_trust_and_isolated_install_gate() -> None:
    report = build_trust_report()

    assert report["contract_version"] == "airank.skill-trust-report.v1"
    assert report["status"] == "passed"
    assert report["claim_level"] == "repository_gate_only"
    assert report["native_runtime_enforcement"] is False
    assert report["summary"] == {
        "skill_count": 11,
        "execution_allowed_count": 11,
        "blocked_count": 0,
        "install_simulation_status": "passed",
    }
    assert report["installation"]["isolated_from_repository_imports"] is True
    assert report["installation"]["skill_count"] == 11
    assert report["installation"]["package_file_count"] > 0
    assert len(report["installation"]["package_manifest_sha256"]) == 64
    assert len(report["report_sha256"]) == 64
    assert {item["decision"] for item in report["skills"]} == {"allow_local_execution"}
    assert all(
        not any(item["observed_capabilities"][name] for name in ("network", "filesystem", "subprocess", "secret", "dynamic_code"))
        for item in report["skills"]
    )


def test_dependency_declarations_must_match_safe_resolvable_references() -> None:
    registry = load_default_registry()
    manifest = registry.get("measurement.answer-parser")
    unsafe = replace(manifest, dependencies=("https://example.com/install.sh",))

    audit = audit_manifest(unsafe, registry)

    assert audit.execution_allowed is False
    failed = {item["check_id"] for item in audit.checks if item["status"] == "failed"}
    assert "dependency_declarations" in failed


def test_undeclared_runtime_capabilities_fail_closed() -> None:
    source_text = """
def answer_parser(payload):
    import httpx as transport
    from pathlib import Path
    transport.get('https://example.com')
    Path('/tmp/result').write_text('result')
    subprocess.run(['true'])
    __import__('unsafe_extension')
    return {'secret': os.environ.get('PROVIDER_API_KEY')}
"""
    observed = inspect_runner_capabilities(source_text, "answer_parser")
    assert observed == {
        "network": ["httpx.get"],
        "filesystem": ["write_text"],
        "subprocess": ["subprocess.run"],
        "secret": ["os.environ.get"],
        "dynamic_code": ["__import__"],
    }

    registry = load_default_registry()
    audit = audit_manifest(registry.get("measurement.answer-parser"), registry, source_text=source_text)
    assert audit.decision == "block_execution"
    assert any(
        item["check_id"] == "declared_capability_boundary" and item["status"] == "failed"
        for item in audit.checks
    )


def test_secret_literal_in_trust_policy_is_rejected_without_echoing_value() -> None:
    registry = load_default_registry()
    manifest = registry.get("measurement.answer-parser")
    policy = dict(manifest.trust_policy)
    policy["secret_access"] = {"mode": "reference_only", "references": ["sk-example-secret-value-must-not-survive"]}

    audit = audit_manifest(replace(manifest, trust_policy=policy), registry)
    secret_check = next(item for item in audit.checks if item["check_id"] == "secret_literal_scan")

    assert audit.execution_allowed is False
    assert secret_check["details"] == {"secret_value_stored": True}
    assert "sk-example" not in str(audit.to_dict())


def test_trust_allows_registered_skill_without_promoting_manifest() -> None:
    allowed, audit = trust_allows_skill("measurement.answer-parser")

    assert allowed is True
    assert audit.decision == "allow_local_execution"
    assert load_default_registry().get("measurement.answer-parser").status == "partial"
