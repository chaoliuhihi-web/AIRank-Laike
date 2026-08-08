from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .core import run_skill
from .registry import SkillManifest, SkillRegistry, load_default_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PACKAGE_ROOT.parents[1]
REQUIRED_SUITES = {"contract", "holdout", "adversarial"}


def stable_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SkillEvalCaseResult:
    case_id: str
    suite: str
    status: str
    input_sha256: str
    output_sha256: str | None
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "suite": self.suite,
            "status": self.status,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class SkillEvaluationReport:
    skill_id: str
    version: str
    manifest_status: str
    local_eval_status: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    executed_suites: tuple[str, ...]
    promotion_eligible: bool
    promotion_blockers: tuple[str, ...]
    evaluation_sha256: str
    cases: tuple[SkillEvalCaseResult, ...]

    def to_dict(self, *, include_cases: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "skill_id": self.skill_id,
            "version": self.version,
            "manifest_status": self.manifest_status,
            "local_eval_status": self.local_eval_status,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "pass_rate": self.pass_rate,
            "executed_suites": list(self.executed_suites),
            "promotion_eligible": self.promotion_eligible,
            "promotion_blockers": list(self.promotion_blockers),
            "evaluation_sha256": self.evaluation_sha256,
        }
        if include_cases:
            payload["cases"] = [case.to_dict() for case in self.cases]
        return payload


def load_external_eval_cases(path: Path | None = None) -> tuple[Mapping[str, Any], ...]:
    corpus_path = path or PACKAGE_ROOT / "evals" / "core_eval_cases.json"
    payload = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("skill eval corpus must contain a cases array")
    seen: set[tuple[str, str]] = set()
    for case in cases:
        key = (str(case.get("skill_id") or ""), str(case.get("case_id") or ""))
        if not all(key) or key in seen:
            raise ValueError("skill eval case ids must be non-empty and unique per skill")
        if case.get("suite") not in {"holdout", "adversarial"}:
            raise ValueError(f"unsupported external eval suite: {case.get('suite')}")
        seen.add(key)
    return tuple(cases)


def load_verified_promotion_evidence(path: Path | None = None) -> dict[str, set[str]]:
    evidence_path = path or PACKAGE_ROOT / "promotion-evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    verified: dict[str, set[str]] = {}
    for item in payload.get("evidence", []):
        skill_id = str(item.get("skill_id") or "")
        evidence_type = str(item.get("evidence_type") or "")
        artifact_path = str(item.get("artifact_path") or "")
        expected_sha256 = str(item.get("sha256") or "")
        target = (REPOSITORY_ROOT / artifact_path).resolve()
        if not skill_id or not evidence_type or not artifact_path or len(expected_sha256) != 64:
            continue
        if REPOSITORY_ROOT != target and REPOSITORY_ROOT not in target.parents:
            continue
        if target.is_file() and file_sha256(target) == expected_sha256:
            verified.setdefault(skill_id, set()).add(evidence_type)
    return verified


def expected_subset_failures(actual: object, expected: object, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return [f"{path}: expected object"]
        for key, value in expected.items():
            if key not in actual:
                failures.append(f"{path}.{key}: missing")
            else:
                failures.extend(expected_subset_failures(actual[key], value, f"{path}.{key}"))
        return failures
    if isinstance(expected, list):
        if actual != expected:
            failures.append(f"{path}: expected exact list {expected!r}, got {actual!r}")
        return failures
    if actual != expected:
        failures.append(f"{path}: expected {expected!r}, got {actual!r}")
    return failures


def quality_rubric_failures(skill_id: str, output: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if skill_id == "measurement.sample-runner" and output.get("status") == "planned":
        tasks = output.get("tasks", [])
        sessions = [task.get("session_id") for task in tasks]
        if len(sessions) != len(set(sessions)):
            failures.append("rubric.independent_sessions: duplicate session_id")
    elif skill_id == "measurement.answer-parser":
        if output.get("brand_rank") is not None and (
            not output.get("brand_mentioned") or output.get("mention_class") != "recommended"
        ):
            failures.append("rubric.no_inferred_rank: rank lacks bound recommendation")
    elif skill_id == "measurement.citation-extractor":
        for citation in output.get("citations", []):
            if not str(citation.get("url") or "").startswith(("http://", "https://")):
                failures.append("rubric.traceable_url: non-http citation retained")
    elif skill_id == "research.intent-miner":
        for question in output.get("questions", []):
            if question.get("source") != "provided_seed" or "volume" in question:
                failures.append("rubric.deduplication: source drift or invented volume")
    elif skill_id == "knowledge.fact-builder":
        if output.get("status") == "pending_review" and output.get("support_mode") != "exact_excerpt":
            failures.append("rubric.source_boundary: pending fact lacks exact support")
    elif skill_id == "governance.claim-verifier":
        if output.get("status") == "supported" and not output.get("support_ids"):
            failures.append("rubric.support_coverage: supported claim lacks ClaimSupport id")
    elif skill_id == "intervention.page-blueprint" and output.get("status") == "draft":
        sections = output.get("sections", [])
        bindings = output.get("claim_bindings", [])
        if not sections:
            failures.append("rubric.fact_binding: draft has no evidence-bound sections")
        for section in sections:
            if not section.get("fact_revision_ids") or not section.get("support_ids"):
                failures.append("rubric.fact_binding: section lacks revision/support ids")
                break
        for binding in bindings:
            source_sha256 = str(binding.get("source_sha256") or "")
            if (
                len(source_sha256) != 64
                or int(binding.get("source_start", -1)) < 0
                or int(binding.get("source_end", -1)) <= int(binding.get("source_start", -1))
            ):
                failures.append("rubric.exact_boundary: claim lacks exact source boundary")
                break
        if not bindings:
            failures.append("rubric.exact_boundary: draft has no claim bindings")
    elif skill_id == "intervention.comparison-builder" and output.get("status") == "draft":
        fairness = output.get("fairness", {})
        if (
            fairness.get("same_scope") is not True
            or fairness.get("coverage_rate") != 1.0
            or fairness.get("dimension_count", 0) < 10
            or fairness.get("ranking_or_score_generated") is not False
        ):
            failures.append("rubric.symmetric_scope: comparison is incomplete or ranked")
        subject_ids = {item.get("subject_id") for item in output.get("subjects", [])}
        dimension_ids = {item.get("dimension_id") for item in output.get("dimensions", [])}
        covered_cells = {
            (item.get("subject_id"), item.get("dimension_id"))
            for item in output.get("claim_bindings", [])
        }
        required_cells = {(subject_id, dimension_id) for subject_id in subject_ids for dimension_id in dimension_ids}
        if not required_cells or not required_cells.issubset(covered_cells):
            failures.append("rubric.symmetric_scope: at least one comparison cell lacks a claim binding")
        for binding in output.get("claim_bindings", []):
            source_sha256 = str(binding.get("source_sha256") or "")
            if (
                len(source_sha256) != 64
                or int(binding.get("source_start", -1)) < 0
                or int(binding.get("source_end", -1)) <= int(binding.get("source_start", -1))
            ):
                failures.append("rubric.exact_boundary: comparison claim lacks exact source boundary")
                break
    elif skill_id == "intervention.explainer-builder" and output.get("status") == "draft":
        quality = output.get("quality", {})
        role_coverage = quality.get("role_coverage", {})
        if not role_coverage or not all(item.get("complete") is True for item in role_coverage.values()):
            failures.append("rubric.role_coverage: one or more evidence roles are incomplete")
        if quality.get("accepted_fact_count", 0) < 12 or quality.get("supported_character_count", 0) < 1400:
            failures.append("rubric.supported_length: explainer evidence volume is below the publishable minimum")
        if quality.get("brand_mention_count", 0) > quality.get("brand_mention_limit", 3):
            failures.append("rubric.brand_insertion: brand mention limit exceeded")
        bindings = output.get("claim_bindings", [])
        if len(bindings) < 12:
            failures.append("rubric.exact_boundary: explainer has too few claim bindings")
        for binding in bindings:
            source_sha256 = str(binding.get("source_sha256") or "")
            if (
                len(source_sha256) != 64
                or int(binding.get("source_start", -1)) < 0
                or int(binding.get("source_end", -1)) <= int(binding.get("source_start", -1))
            ):
                failures.append("rubric.exact_boundary: explainer claim lacks exact source boundary")
                break
    elif skill_id == "delivery.retest-report" and output.get("status") == "observed":
        conclusion = str(output.get("conclusion") or "")
        if not all(marker in conclusion for marker in ("观察", "可能", "不能据此证明因果")):
            failures.append("rubric.attribution_language: conclusion overstates causality")
    return failures


def evaluate_manifest(
    manifest: SkillManifest,
    *,
    external_cases: tuple[Mapping[str, Any], ...] | None = None,
    verified_evidence: Mapping[str, set[str]] | None = None,
) -> SkillEvaluationReport:
    cases = [dict(case, suite="contract") for case in manifest.eval_cases]
    cases.extend(
        dict(case)
        for case in (external_cases if external_cases is not None else load_external_eval_cases())
        if case.get("skill_id") == manifest.skill_id
    )
    input_validator = Draft202012Validator(manifest.input_schema)
    output_validator = Draft202012Validator(manifest.output_schema)
    case_results: list[SkillEvalCaseResult] = []
    for case in cases:
        case_input = dict(case["input"])
        failures: list[str] = []
        output: dict[str, Any] | None = None
        try:
            input_validator.validate(case_input)
            output = run_skill(manifest.skill_id, case_input)
            output_validator.validate(output)
            failures.extend(expected_subset_failures(output, case["expected"]))
            failures.extend(quality_rubric_failures(manifest.skill_id, output))
        except Exception as exc:  # evaluation must record failures, not hide them
            failures.append(f"execution: {type(exc).__name__}: {exc}")
        case_results.append(
            SkillEvalCaseResult(
                case_id=str(case["case_id"]),
                suite=str(case["suite"]),
                status="passed" if not failures else "failed",
                input_sha256=stable_sha256(case_input),
                output_sha256=stable_sha256(output) if output is not None else None,
                failures=tuple(failures),
            )
        )

    passed = sum(result.status == "passed" for result in case_results)
    total = len(case_results)
    pass_rate = round(passed / total, 6) if total else 0.0
    executed_suites = tuple(sorted({result.suite for result in case_results}))
    policy = manifest.promotion_policy
    blockers: list[str] = []
    required_suites = set(policy.get("required_suites", REQUIRED_SUITES))
    missing_suites = sorted(required_suites - set(executed_suites))
    if missing_suites:
        blockers.append(f"missing_eval_suites:{','.join(missing_suites)}")
    if pass_rate < float(policy.get("minimum_pass_rate", 1.0)):
        blockers.append(f"eval_pass_rate:{pass_rate:.6f}")
    if passed != total:
        blockers.append(f"failed_eval_cases:{total - passed}")
    available_evidence = (verified_evidence or load_verified_promotion_evidence()).get(manifest.skill_id, set())
    for evidence_type in policy.get("required_evidence", []):
        if evidence_type not in available_evidence:
            blockers.append(f"missing_promotion_evidence:{evidence_type}")

    digest_payload = [result.to_dict() for result in case_results]
    return SkillEvaluationReport(
        skill_id=manifest.skill_id,
        version=manifest.version,
        manifest_status=manifest.status,
        local_eval_status="passed" if passed == total and total else "failed",
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        pass_rate=pass_rate,
        executed_suites=executed_suites,
        promotion_eligible=not blockers,
        promotion_blockers=tuple(blockers),
        evaluation_sha256=stable_sha256(digest_payload),
        cases=tuple(case_results),
    )


def evaluate_registry(registry: SkillRegistry | None = None) -> tuple[SkillEvaluationReport, ...]:
    selected_registry = registry or load_default_registry()
    external_cases = load_external_eval_cases()
    verified_evidence = load_verified_promotion_evidence()
    return tuple(
        evaluate_manifest(
            manifest,
            external_cases=external_cases,
            verified_evidence=verified_evidence,
        )
        for manifest in selected_registry.list()
    )


def build_promotion_ledger(registry: SkillRegistry | None = None) -> dict[str, Any]:
    reports = evaluate_registry(registry)
    source_files = {
        "registry": PACKAGE_ROOT / "registry.json",
        "eval_corpus": PACKAGE_ROOT / "evals" / "core_eval_cases.json",
        "promotion_evidence": PACKAGE_ROOT / "promotion-evidence.json",
        "implementation": Path(__file__).with_name("core.py"),
        "evaluation_engine": Path(__file__),
    }
    return {
        "ledger_version": "1.0.0",
        "source_sha256": {name: file_sha256(path) for name, path in source_files.items()},
        "skills": [
            {
                **report.to_dict(include_cases=False),
                "decision": "promote_ready" if report.promotion_eligible else "retain_partial",
            }
            for report in reports
        ],
    }
