from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


ALLOWED_CATEGORIES = {"measurement", "research", "knowledge", "intervention", "governance", "delivery"}
ALLOWED_STATUSES = {"ready", "partial", "blocked", "disabled", "dev_only"}


@dataclass(frozen=True)
class SkillManifest:
    skill_id: str
    version: str
    category: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    dependencies: tuple[str, ...]
    provider_requirements: tuple[str, ...]
    evidence_level: tuple[str, ...]
    fact_policy: Mapping[str, Any]
    failure_policy: Mapping[str, Any]
    quality_rubric: tuple[Mapping[str, Any], ...]
    eval_cases: tuple[Mapping[str, Any], ...]
    promotion_policy: Mapping[str, Any]
    status: str
    entrypoint: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SkillManifest":
        if payload["category"] not in ALLOWED_CATEGORIES:
            raise ValueError(f"unsupported skill category: {payload['category']}")
        if payload["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"unsupported skill status: {payload['status']}")
        Draft202012Validator.check_schema(payload["input_schema"])
        Draft202012Validator.check_schema(payload["output_schema"])
        if not payload["eval_cases"]:
            raise ValueError(f"{payload['skill_id']} must include executable eval_cases")
        if not payload["quality_rubric"]:
            raise ValueError(f"{payload['skill_id']} must include quality_rubric")
        return cls(
            skill_id=str(payload["skill_id"]),
            version=str(payload["version"]),
            category=str(payload["category"]),
            input_schema=payload["input_schema"],
            output_schema=payload["output_schema"],
            dependencies=tuple(payload["dependencies"]),
            provider_requirements=tuple(payload["provider_requirements"]),
            evidence_level=tuple(payload["evidence_level"]),
            fact_policy=payload["fact_policy"],
            failure_policy=payload["failure_policy"],
            quality_rubric=tuple(payload["quality_rubric"]),
            eval_cases=tuple(payload["eval_cases"]),
            promotion_policy=payload["promotion_policy"],
            status=str(payload["status"]),
            entrypoint=str(payload["entrypoint"]),
        )


class SkillRegistry:
    def __init__(self, manifests: list[SkillManifest]) -> None:
        self._manifests = {manifest.skill_id: manifest for manifest in manifests}
        if len(self._manifests) != len(manifests):
            raise ValueError("skill_id values must be unique")

    def get(self, skill_id: str) -> SkillManifest:
        try:
            return self._manifests[skill_id]
        except KeyError as exc:
            raise KeyError(f"unknown AIRank skill: {skill_id}") from exc

    def list(self) -> tuple[SkillManifest, ...]:
        return tuple(sorted(self._manifests.values(), key=lambda manifest: manifest.skill_id))


def load_default_registry() -> SkillRegistry:
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    schema = json.loads((root / "registry.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    return SkillRegistry([SkillManifest.from_dict(item) for item in payload["skills"]])
