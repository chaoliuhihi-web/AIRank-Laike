from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata
from typing import Iterable, Literal, Sequence

from airank_domain import sha256_text


TAXONOMY_VERSION = "airank-question-taxonomy-v1.2.0"

QuestionType = Literal["purchase", "compare", "select", "trust", "price", "risk", "scenario", "local", "alternative"]
CohortType = Literal["blind", "assisted", "comparison", "fact_verification"]
PromptStyle = Literal["exploratory", "comparative", "factual", "procedural", "evaluative"]
TemporalScope = Literal["evergreen", "current", "historical"]
QuestionScenario = Literal["generic", "b2b_procurement", "local_selection", "replacement", "risk_validation"]
SourceKind = Literal["provided_seed", "template_candidate", "observed_query", "imported"]


@dataclass(frozen=True)
class ObservedQuestionSeed:
    question_text: str
    source_ref: str
    occurrence_count: int = 1
    observed_at: str | None = None
    region: str | None = None
    evidence_grade: str = "user_provided_snapshot"

    def provenance(self) -> dict[str, object]:
        return {
            "source_ref": self.source_ref,
            "source_kind": "observed_query",
            "occurrence_count": self.occurrence_count,
            "observed_at": self.observed_at,
            "region": self.region,
            "evidence_grade": self.evidence_grade,
        }


def normalize_question(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def question_dedupe_sha256(value: str) -> str:
    normalized = normalize_question(value).casefold()
    normalized = re.sub(r"[\s。！？!?，,；;：:、]+", "", normalized)
    return sha256_text(normalized)


def _contains_any(value: str, markers: Iterable[str]) -> bool:
    folded = value.casefold()
    return any(marker.casefold() in folded for marker in markers if marker)


def _question_type(question: str, regions: Sequence[str]) -> QuestionType:
    if _contains_any(question, ("替代", "替换", "替代品", "alternative", "replace")):
        return "alternative"
    if _contains_any(question, tuple(regions) + ("本地", "附近", "当地", "哪家", "near me", "local provider")):
        return "local"
    if _contains_any(question, ("对比", "比较", "区别", "还是", "哪个更", "相比", "compare", " vs ", "difference", "better than")):
        return "compare"
    if _contains_any(question, ("价格", "报价", "多少钱", "费用", "收费", "price", "cost", "fee", "quote")):
        return "price"
    if _contains_any(question, ("风险", "缺点", "问题", "避坑", "隐患", "risk", "drawback", "pitfall", "concern")):
        return "risk"
    if _contains_any(question, ("靠谱", "可信", "资质", "案例", "口碑", "真实性", "reliable", "credible", "case study", "certification")):
        return "trust"
    if _contains_any(question, ("场景", "适合谁", "适用于", "怎么用", "用途", "use case", "suitable for", "how to use")):
        return "scenario"
    if _contains_any(question, ("怎么选", "如何选择", "推荐", "有哪些", "哪一个", "how to choose", "which", "recommend", "options")):
        return "select"
    return "purchase"


def _temporal_scope(question: str) -> TemporalScope:
    if _contains_any(question, ("过去", "历史", "曾经", "此前")):
        return "historical"
    if _contains_any(question, ("最新", "目前", "现在", "今年", "近期", "latest", "current", "recent")) or re.search(r"20\d{2}", question):
        return "current"
    return "evergreen"


def _cohort_type(
    question: str,
    target_names: Sequence[str],
    competitor_names: Sequence[str],
    question_type: QuestionType,
) -> CohortType:
    contains_target = _contains_any(question, target_names)
    contains_competitor = _contains_any(question, competitor_names)
    if question_type in {"compare", "alternative"} and (contains_target or contains_competitor):
        return "comparison"
    if contains_target and _contains_any(question, ("是否", "有没有", "支持", "成立", "准确", "真实吗", "does ", "is ", "support", "accurate", "true")):
        return "fact_verification"
    if contains_target:
        return "assisted"
    if contains_competitor:
        return "comparison"
    return "blind"


@dataclass(frozen=True)
class GovernedQuestion:
    question_text: str
    dedupe_sha256: str
    question_version_id: str
    taxonomy_version: str
    question_type: QuestionType
    intent_level: Literal["high", "medium", "low"]
    buyer_stage: Literal["awareness", "consideration", "decision"]
    prompt_style: PromptStyle
    temporal_scope: TemporalScope
    scenario: QuestionScenario
    region: str | None
    cohort_type: CohortType
    source_kind: SourceKind
    source_ref: str
    evidence_level: Literal["provided_seed", "template_candidate", "observed_query", "imported"]
    observed_query: bool

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


def govern_question(
    question_text: str,
    *,
    target_names: Sequence[str] = (),
    competitor_names: Sequence[str] = (),
    regions: Sequence[str] = (),
    source_kind: SourceKind = "provided_seed",
    source_ref: str = "manual",
) -> GovernedQuestion:
    question = normalize_question(question_text)
    if len(question) < 4:
        raise ValueError("question must contain at least 4 characters")
    question_type = _question_type(question, regions)
    intent_level: Literal["high", "medium", "low"] = (
        "high" if question_type in {"compare", "select", "price", "risk", "local", "alternative"}
        else "medium" if question_type in {"trust", "scenario"}
        else "low"
    )
    buyer_stage: Literal["awareness", "consideration", "decision"] = (
        "decision" if question_type in {"compare", "select", "price", "local", "alternative"}
        else "consideration" if question_type in {"risk", "trust", "scenario"}
        else "awareness"
    )
    prompt_style: PromptStyle = (
        "comparative" if question_type in {"compare", "alternative"}
        else "factual" if question_type in {"trust", "price"}
        else "procedural" if question_type in {"select", "local"}
        else "evaluative" if question_type == "risk"
        else "exploratory"
    )
    region = next((item for item in regions if item and item.casefold() in question.casefold()), None)
    scenario: QuestionScenario = (
        "local_selection" if region or question_type == "local"
        else "replacement" if question_type == "alternative"
        else "risk_validation" if question_type in {"risk", "trust"}
        else "b2b_procurement" if _contains_any(question, ("企业", "采购", "团队", "公司", "B2B", "enterprise", "business", "company", "procurement", "team", "manufacturer"))
        else "generic"
    )
    cohort_type = _cohort_type(question, target_names, competitor_names, question_type)
    if cohort_type == "fact_verification":
        intent_level = "high"
        buyer_stage = "decision"
        prompt_style = "factual"
        scenario = "risk_validation"
    dedupe_sha256 = question_dedupe_sha256(question)
    version_payload = {
        "contract": "airank.buyer-question.v1",
        "taxonomy_version": TAXONOMY_VERSION,
        "question_text": question,
        "question_type": question_type,
        "intent_level": intent_level,
        "buyer_stage": buyer_stage,
        "prompt_style": prompt_style,
        "temporal_scope": _temporal_scope(question),
        "scenario": scenario,
        "region": region,
        "cohort_type": cohort_type,
        "source_kind": source_kind,
        "source_ref": source_ref,
    }
    version_sha = sha256_text(json.dumps(version_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return GovernedQuestion(
        question_text=question,
        dedupe_sha256=dedupe_sha256,
        question_version_id=f"question_v_{version_sha[:20]}",
        taxonomy_version=TAXONOMY_VERSION,
        question_type=question_type,
        intent_level=intent_level,
        buyer_stage=buyer_stage,
        prompt_style=prompt_style,
        temporal_scope=_temporal_scope(question),
        scenario=scenario,
        region=region,
        cohort_type=cohort_type,
        source_kind=source_kind,
        source_ref=source_ref,
        evidence_level=source_kind,
        observed_query=source_kind == "observed_query",
    )


def compile_question_candidates(
    *,
    brand_name: str,
    company_names: Sequence[str],
    product_terms: Sequence[str],
    competitor_names: Sequence[str],
    regions: Sequence[str],
    seed_questions: Sequence[str],
    include_template_candidates: bool,
    observed_questions: Sequence[ObservedQuestionSeed] = (),
) -> tuple[str, str, list[dict[str, object]]]:
    entries: list[tuple[str, SourceKind, str, dict[str, object]]] = [
        (
            value.question_text,
            "observed_query",
            value.source_ref,
            value.provenance(),
        )
        for value in observed_questions
        if normalize_question(value.question_text)
    ]
    entries.extend([
        (
            value,
            "provided_seed",
            f"seed:{index}",
            {
                "source_ref": f"seed:{index}",
                "source_kind": "provided_seed",
                "evidence_grade": "provided_seed",
            },
        )
        for index, value in enumerate(seed_questions, start=1)
        if normalize_question(value)
    ])
    if include_template_candidates:
        for index, product in enumerate(product_terms, start=1):
            product = normalize_question(product)
            if not product:
                continue
            entries.extend([
                (
                    f"企业应该如何选择{product}？",
                    "template_candidate",
                    f"template:product-selection:{index}",
                    {"source_ref": f"template:product-selection:{index}", "source_kind": "template_candidate", "evidence_grade": "template_candidate"},
                ),
                (
                    f"{product}常见风险和避坑点有哪些？",
                    "template_candidate",
                    f"template:product-risk:{index}",
                    {"source_ref": f"template:product-risk:{index}", "source_kind": "template_candidate", "evidence_grade": "template_candidate"},
                ),
                (
                    f"{product}的价格和服务模式通常如何比较？",
                    "template_candidate",
                    f"template:product-price:{index}",
                    {"source_ref": f"template:product-price:{index}", "source_kind": "template_candidate", "evidence_grade": "template_candidate"},
                ),
            ])
            for region_index, region in enumerate(regions, start=1):
                source_ref = f"template:local:{index}:{region_index}"
                entries.append(
                    (
                        f"{region}有哪些适合企业的{product}服务商？",
                        "template_candidate",
                        source_ref,
                        {"source_ref": source_ref, "source_kind": "template_candidate", "evidence_grade": "template_candidate"},
                    )
                )
            for competitor_index, competitor in enumerate(competitor_names, start=1):
                if brand_name:
                    source_ref = f"template:comparison:{index}:{competitor_index}"
                    entries.append(
                        (
                            f"{brand_name}和{competitor}在{product}方面有什么区别？",
                            "template_candidate",
                            source_ref,
                            {"source_ref": source_ref, "source_kind": "template_candidate", "evidence_grade": "template_candidate"},
                        )
                    )

    targets = tuple(dict.fromkeys(value for value in (brand_name, *company_names) if value))
    by_key: dict[str, dict[str, object]] = {}
    for question_text, source_kind, source_ref, provenance in entries:
        governed = govern_question(
            question_text,
            target_names=targets,
            competitor_names=competitor_names,
            regions=regions,
            source_kind=source_kind,
            source_ref=source_ref,
        )
        existing = by_key.get(governed.dedupe_sha256)
        if existing is not None:
            refs = existing.setdefault("deduplicated_source_refs", [])
            if isinstance(refs, list) and source_ref not in refs:
                refs.append(source_ref)
            records = existing.setdefault("provenance_records", [])
            if isinstance(records, list) and provenance not in records:
                records.append(provenance)
            continue
        item = governed.as_dict()
        item["deduplicated_source_refs"] = [source_ref]
        item["provenance_records"] = [provenance]
        by_key[governed.dedupe_sha256] = item

    input_payload = {
        "contract": "airank.question-map-input.v1",
        "taxonomy_version": TAXONOMY_VERSION,
        "brand_name": normalize_question(brand_name),
        "company_names": [normalize_question(value) for value in company_names if normalize_question(value)],
        "product_terms": [normalize_question(value) for value in product_terms if normalize_question(value)],
        "competitor_names": [normalize_question(value) for value in competitor_names if normalize_question(value)],
        "regions": [normalize_question(value) for value in regions if normalize_question(value)],
        "seed_questions": [normalize_question(value) for value in seed_questions if normalize_question(value)],
        "observed_questions": [
            {
                "question_text": normalize_question(value.question_text),
                **value.provenance(),
            }
            for value in observed_questions
            if normalize_question(value.question_text)
        ],
        "include_template_candidates": include_template_candidates,
    }
    input_sha256 = sha256_text(json.dumps(input_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return f"question_map_{input_sha256[:20]}", input_sha256, list(by_key.values())
