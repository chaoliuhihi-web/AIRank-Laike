from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
from typing import Any, Mapping


class PromptCohortType(str, Enum):
    BLIND = "blind"
    ASSISTED = "assisted"
    COMPARISON = "comparison"
    FACT_VERIFICATION = "fact_verification"


class CollectorSurface(str, Enum):
    API = "api"
    WEB = "web"
    APP = "app"
    MANUAL_IMPORT = "manual_import"


class SampleStatus(str, Enum):
    VALID = "valid"
    FAILED = "failed"
    BLOCKED = "blocked"


class MentionClass(str, Enum):
    RECOMMENDED = "recommended"
    CANDIDATE = "candidate"
    MENTIONED = "mentioned"
    NEGATIVE = "negative"
    NOT_MENTIONED = "not_mentioned"
    UNKNOWN = "unknown"


class EvidenceLevel(str, Enum):
    PROVIDER_API = "provider_api"
    CONSUMER_WEB = "consumer_web"
    CONSUMER_APP = "consumer_app"
    MANUAL_IMPORT = "manual_import"


SURFACE_EVIDENCE_LEVEL: dict[CollectorSurface, EvidenceLevel] = {
    CollectorSurface.API: EvidenceLevel.PROVIDER_API,
    CollectorSurface.WEB: EvidenceLevel.CONSUMER_WEB,
    CollectorSurface.APP: EvidenceLevel.CONSUMER_APP,
    CollectorSurface.MANUAL_IMPORT: EvidenceLevel.MANUAL_IMPORT,
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(payload)


def stable_prompt_version_id(*, cohort_type: PromptCohortType, prompt_text: str, template_version: str = "v1") -> str:
    digest = canonical_json_sha256(
        {"cohort_type": cohort_type.value, "prompt_text": prompt_text, "template_version": template_version}
    )
    return f"prompt_v_{digest[:16]}"


@dataclass(frozen=True)
class EntityMention:
    canonical_name: str
    matched_name: str
    entity_type: str
    start: int
    end: int


@dataclass(frozen=True)
class BrandEntity:
    canonical_name: str
    aliases: tuple[str, ...] = ()
    company_names: tuple[str, ...] = ()
    product_names: tuple[str, ...] = ()

    def names_by_type(self) -> tuple[tuple[str, str], ...]:
        values = [(self.canonical_name, "brand")]
        values.extend((value, "alias") for value in self.aliases)
        values.extend((value, "company") for value in self.company_names)
        values.extend((value, "product") for value in self.product_names)
        seen: set[str] = set()
        result: list[tuple[str, str]] = []
        for name, entity_type in values:
            normalized = name.strip()
            key = normalized.casefold()
            if len(normalized) < 2 or key in seen:
                continue
            seen.add(key)
            result.append((normalized, entity_type))
        return tuple(result)


def find_entity_mentions(text: str, entity: BrandEntity) -> tuple[EntityMention, ...]:
    folded = text.casefold()
    mentions: list[EntityMention] = []
    occupied: set[tuple[int, int]] = set()
    for name, entity_type in sorted(entity.names_by_type(), key=lambda item: len(item[0]), reverse=True):
        folded_name = name.casefold()
        start = 0
        while True:
            index = folded.find(folded_name, start)
            if index < 0:
                break
            boundary = (index, index + len(name))
            if boundary not in occupied:
                occupied.add(boundary)
                mentions.append(
                    EntityMention(
                        canonical_name=entity.canonical_name,
                        matched_name=text[index : index + len(name)],
                        entity_type=entity_type,
                        start=index,
                        end=index + len(name),
                    )
                )
            start = index + len(folded_name)
    return tuple(sorted(mentions, key=lambda mention: (mention.start, mention.end)))


@dataclass(frozen=True)
class PromptVersion:
    prompt_version_id: str
    cohort_type: PromptCohortType
    prompt_text: str
    template_version: str
    prompt_sha256: str
    created_at: datetime
    target_entity: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        cohort_type: PromptCohortType,
        prompt_text: str,
        created_at: datetime,
        template_version: str = "v1",
        target_entity: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PromptVersion":
        normalized = prompt_text.strip()
        if not normalized:
            raise ValueError("prompt_text is required")
        if cohort_type == PromptCohortType.BLIND and target_entity and target_entity in normalized:
            raise ValueError("blind prompt must not reveal target_entity")
        return cls(
            prompt_version_id=stable_prompt_version_id(
                cohort_type=cohort_type,
                prompt_text=normalized,
                template_version=template_version,
            ),
            cohort_type=cohort_type,
            prompt_text=normalized,
            template_version=template_version,
            prompt_sha256=sha256_text(normalized),
            created_at=created_at,
            target_entity=target_entity,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class SampleContext:
    prompt_version_id: str
    cohort_type: PromptCohortType
    sample_index: int
    session_id: str
    surface: CollectorSurface
    evidence_level: EvidenceLevel
    provider: str
    captured_at: datetime
    model_name: str | None = None
    model_version: str | None = None
    search_enabled: bool | None = None
    locale: str = "zh-CN"
    region: str | None = None

    def __post_init__(self) -> None:
        if self.sample_index < 1:
            raise ValueError("sample_index must be positive")
        if not self.session_id.strip():
            raise ValueError("session_id is required for independent sampling")
        expected = SURFACE_EVIDENCE_LEVEL[self.surface]
        if self.evidence_level != expected:
            raise ValueError(f"surface={self.surface.value} requires evidence_level={expected.value}")


@dataclass(frozen=True)
class MeasurementSample:
    sample_id: str
    question_id: str
    context: SampleContext
    status: SampleStatus
    answer_text: str | None = None
    answer_sha256: str | None = None
    raw_response_sha256: str | None = None
    mention_class: MentionClass = MentionClass.UNKNOWN
    brand_rank: int | None = None
    citation_count: int = 0
    citation_support_score: float | None = None
    fact_accuracy: float | None = None
    failure_code: str | None = None

    def __post_init__(self) -> None:
        answer = (self.answer_text or "").strip()
        if self.status == SampleStatus.VALID:
            if not answer:
                raise ValueError("valid sample requires answer_text")
            digest = sha256_text(answer)
            if self.answer_sha256 and self.answer_sha256 != digest:
                raise ValueError("answer_sha256 does not match answer_text")
            if not self.answer_sha256:
                object.__setattr__(self, "answer_sha256", digest)
            if self.mention_class == MentionClass.UNKNOWN:
                raise ValueError("valid sample requires an explicit mention_class, including not_mentioned")
            if self.failure_code:
                raise ValueError("valid sample cannot include failure_code")
        else:
            if not self.failure_code:
                raise ValueError("failed or blocked sample requires failure_code")
            if self.brand_rank is not None:
                raise ValueError("failed or blocked sample cannot include brand_rank")
        if self.brand_rank is not None and self.brand_rank < 1:
            raise ValueError("brand_rank must be positive")
        if self.citation_count < 0:
            raise ValueError("citation_count cannot be negative")
        for field_name, value in (
            ("citation_support_score", self.citation_support_score),
            ("fact_accuracy", self.fact_accuracy),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"{field_name} must be between 0 and 1")

    @property
    def included_in_effective_denominator(self) -> bool:
        return self.status == SampleStatus.VALID
