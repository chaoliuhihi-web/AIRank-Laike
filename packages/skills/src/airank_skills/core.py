from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import re
from typing import Any
from uuid import uuid4

from airank_domain.measurement import BrandEntity, PromptCohortType, find_entity_mentions, sha256_text


SkillRunner = Callable[[dict[str, Any]], dict[str, Any]]


def sample_runner(payload: dict[str, Any]) -> dict[str, Any]:
    questions = [str(value).strip() for value in payload.get("questions", []) if str(value).strip()]
    providers = [str(value).strip() for value in payload.get("providers", []) if str(value).strip()]
    surfaces = [str(value).strip() for value in payload.get("surfaces", ["web"]) if str(value).strip()]
    repetitions = int(payload.get("repetitions", 3))
    cohort = PromptCohortType(str(payload.get("cohort_type", "blind")))
    if not questions or not providers or not surfaces:
        return {"status": "blocked", "failure_code": "SAMPLE_SCOPE_EMPTY", "tasks": []}
    if repetitions < 1 or repetitions > 20:
        return {"status": "blocked", "failure_code": "REPETITIONS_OUT_OF_RANGE", "tasks": []}
    tasks = []
    for question_index, question in enumerate(questions, start=1):
        prompt_version_id = f"prompt_v_{sha256_text(f'{cohort.value}:{question}')[:16]}"
        for provider in providers:
            for surface in surfaces:
                for sample_index in range(1, repetitions + 1):
                    tasks.append(
                        {
                            "question_index": question_index,
                            "question_text": question,
                            "provider": provider,
                            "surface": surface,
                            "cohort_type": cohort.value,
                            "prompt_version_id": prompt_version_id,
                            "sample_index": sample_index,
                            "session_id": f"session_{uuid4().hex}",
                        }
                    )
    return {"status": "planned", "task_count": len(tasks), "tasks": tasks}


def answer_parser(payload: dict[str, Any]) -> dict[str, Any]:
    answer = str(payload.get("answer_text", "")).strip()
    brand = str(payload.get("brand_name", "")).strip()
    entity = BrandEntity(
        canonical_name=brand,
        aliases=tuple(payload.get("aliases", [])),
        company_names=tuple(payload.get("company_names", [])),
        product_names=tuple(payload.get("product_names", [])),
    )
    if not answer:
        return {"status": "failed", "failure_code": "ANSWER_EMPTY"}
    mentions = find_entity_mentions(answer, entity)
    explicit_rank = None
    for name, _entity_type in entity.names_by_type():
        match = re.search(
            rf"(?:第\s*(\d+)\s*[名位]\s*[:：、-]?\s*{re.escape(name)}|"
            rf"{re.escape(name)}\s*(?:排名|位列|排在)?\s*第\s*(\d+)\s*[名位])",
            answer,
        )
        if match:
            explicit_rank = int(next(group for group in match.groups() if group is not None))
            break
    if not mentions:
        mention_class = "not_mentioned"
    else:
        first = mentions[0]
        window = answer[max(0, first.start - 100) : first.end + 180]
        if any(marker in window for marker in ("不推荐", "不建议", "风险", "谨慎")):
            mention_class = "negative"
        elif explicit_rank is not None or any(marker in window for marker in ("推荐", "首选", "优先考虑", "值得选择")):
            mention_class = "recommended"
        elif any(marker in window for marker in ("候选", "可以考虑", "备选", "适合")):
            mention_class = "candidate"
        else:
            mention_class = "mentioned"
    return {
        "status": "valid",
        "answer_sha256": sha256_text(answer),
        "brand_mentioned": bool(mentions),
        "mention_class": mention_class,
        "brand_rank": explicit_rank,
        "entity_mentions": [mention.__dict__ for mention in mentions],
        "confidence": None,
    }


def citation_extractor(payload: dict[str, Any]) -> dict[str, Any]:
    citations = []
    seen = set()
    for item in payload.get("native_citations", []):
        url = str(item.get("url", "")).strip()
        if not re.match(r"^https?://", url) or url in seen:
            continue
        seen.add(url)
        citations.append({"url": url, "title": str(item.get("title", "")).strip(), "source": "provider_native"})
    return {
        "status": "valid",
        "citation_count": len(citations),
        "citations": citations,
        "missing_reason": None if citations else "provider_returned_no_traceable_native_citation",
    }


def intent_miner(payload: dict[str, Any]) -> dict[str, Any]:
    unique: list[str] = []
    seen: set[str] = set()
    for raw in payload.get("seed_questions", []):
        question = re.sub(r"\s+", " ", str(raw)).strip()
        key = question.casefold()
        if not question or key in seen:
            continue
        seen.add(key)
        unique.append(question)
    questions = []
    for question in unique:
        if any(marker in question for marker in ("对比", "比较", "区别", "还是")):
            intent = "comparison"
        elif any(marker in question for marker in ("价格", "报价", "多少钱")):
            intent = "price"
        elif any(marker in question for marker in ("风险", "缺点", "问题")):
            intent = "risk"
        else:
            intent = "selection"
        questions.append({"question_text": question, "intent": intent, "source": "provided_seed", "version": "v1"})
    return {"status": "valid" if questions else "blocked", "question_count": len(questions), "questions": questions}


def fact_builder(payload: dict[str, Any]) -> dict[str, Any]:
    source_id = str(payload.get("source_id", "")).strip()
    excerpt = str(payload.get("source_excerpt", "")).strip()
    claim = str(payload.get("claim", "")).strip()
    if not source_id or not excerpt or not claim:
        return {"status": "blocked", "failure_code": "SOURCE_EVIDENCE_REQUIRED"}
    source_sentences = {
        sentence.strip()
        for sentence in re.split(r"[。！？!?；;\n]+", excerpt)
        if sentence.strip()
    }
    supported = claim == excerpt or claim in source_sentences
    return {
        "status": "pending_review" if supported else "needs_evidence",
        "fact_text": claim,
        "source_id": source_id,
        "source_sha256": sha256_text(excerpt),
        "source_excerpt": excerpt,
        "support_mode": "exact_excerpt" if supported else "not_supported",
    }


def claim_verifier(payload: dict[str, Any]) -> dict[str, Any]:
    claim = str(payload.get("claim", "")).strip()
    approved_facts = payload.get("approved_facts", [])
    now = datetime.now(timezone.utc)

    def is_eligible(fact: dict[str, Any]) -> bool:
        valid_until = fact.get("valid_until")
        if valid_until:
            try:
                expires_at = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
            except ValueError:
                return False
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                return False
        return (
            fact.get("status") == "approved"
            and fact.get("eligible_for_generation") is True
            and fact.get("conflict_status", "none") != "open"
            and bool(fact.get("support_ids"))
            and claim == str(fact.get("fact_text", "")).strip()
        )

    supports = [fact for fact in approved_facts if is_eligible(fact)]
    return {
        "status": "supported" if supports else "needs_evidence",
        "claim": claim,
        "support_ids": sorted({str(support_id) for fact in supports for support_id in fact.get("support_ids", [])}),
        "fact_ids": [str(fact.get("fact_id")) for fact in supports],
    }


def page_blueprint(payload: dict[str, Any]) -> dict[str, Any]:
    facts = payload.get("facts", [])
    if not facts:
        return {"status": "needs_evidence", "missing_fact_ids": [], "sections": []}
    unapproved = [fact for fact in facts if fact.get("status") != "approved" or not fact.get("support_ids")]
    if unapproved:
        return {"status": "needs_evidence", "missing_fact_ids": [fact.get("fact_id") for fact in unapproved], "sections": []}
    return {
        "status": "draft",
        "sections": [
            {"section_type": "summary", "fact_ids": [fact["fact_id"] for fact in facts]},
            {"section_type": "evidence", "support_ids": sorted({support for fact in facts for support in fact["support_ids"]})},
            {"section_type": "faq", "fact_ids": [fact["fact_id"] for fact in facts]},
        ],
    }


def retest_report(payload: dict[str, Any]) -> dict[str, Any]:
    baseline = payload.get("baseline", {})
    followup = payload.get("followup", {})
    comparable = all(
        baseline.get(key) == followup.get(key)
        for key in ("cohort_type", "provider_scope", "collector_surfaces", "question_version")
    )
    if not comparable:
        return {"status": "blocked", "failure_code": "NON_COMPARABLE_WINDOWS", "conclusion": "无法比较不同口径的样本。"}
    baseline_rate = float(baseline.get("mention_rate", 0))
    followup_rate = float(followup.get("mention_rate", 0))
    baseline_count = int(baseline.get("valid_sample_count", 0))
    followup_count = int(followup.get("valid_sample_count", 0))
    if not 0 <= baseline_rate <= 1 or not 0 <= followup_rate <= 1 or baseline_count <= 0 or followup_count <= 0:
        return {
            "status": "blocked",
            "failure_code": "INVALID_OBSERVATION_METRICS",
            "conclusion": "观察窗口缺少有效样本或指标超出合法范围。",
        }
    delta = round(followup_rate - baseline_rate, 6)
    sample_floor = min(baseline_count, followup_count)
    confidence = "high" if sample_floor >= 30 else "medium" if sample_floor >= 10 else "low"
    return {
        "status": "observed",
        "mention_rate_delta": delta,
        "confidence": confidence,
        "conclusion": f"观察到品牌提及率变化 {delta:+.2%}；该变化可能与观察窗口内的干预相关，不能据此证明因果关系。",
    }


SKILL_RUNNERS: dict[str, SkillRunner] = {
    "measurement.sample-runner": sample_runner,
    "measurement.answer-parser": answer_parser,
    "measurement.citation-extractor": citation_extractor,
    "research.intent-miner": intent_miner,
    "knowledge.fact-builder": fact_builder,
    "governance.claim-verifier": claim_verifier,
    "intervention.page-blueprint": page_blueprint,
    "delivery.retest-report": retest_report,
}


def run_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        runner = SKILL_RUNNERS[skill_id]
    except KeyError as exc:
        raise KeyError(f"unknown AIRank skill runner: {skill_id}") from exc
    return runner(payload)
