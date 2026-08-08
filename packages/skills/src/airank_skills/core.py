from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import uuid4

from airank_domain import govern_question, normalize_question, question_dedupe_sha256
from airank_domain.measurement import BrandEntity, PromptCohortType, find_entity_mentions, sha256_text


SkillRunner = Callable[[dict[str, Any]], dict[str, Any]]
OBSERVATION_SOURCE_REF_PATTERN = re.compile(r"^observation:qobatch_[0-9a-f]{20}:qobs_[0-9a-f]{20}$")
OBSERVATION_EVIDENCE_GRADES = {"user_provided_snapshot", "connector_verified", "provider_sample_verified"}


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
    unique: list[tuple[str, str, str, dict[str, Any]]] = []
    seen: set[str] = set()
    entries: list[tuple[Any, str, str, dict[str, Any]]] = []
    for item in payload.get("observed_questions", []):
        if not isinstance(item, dict):
            continue
        source_ref = str(item.get("source_ref", "")).strip()
        evidence_grade = str(item.get("evidence_grade", "")).strip()
        if not OBSERVATION_SOURCE_REF_PATTERN.fullmatch(source_ref):
            continue
        if evidence_grade not in OBSERVATION_EVIDENCE_GRADES:
            continue
        try:
            occurrence_count = int(item.get("occurrence_count", 1))
        except (TypeError, ValueError):
            continue
        if occurrence_count < 1:
            continue
        entries.append((
            item.get("question_text", ""),
            "observed_query",
            source_ref,
            {
                "source_ref": source_ref,
                "source_kind": "observed_query",
                "evidence_grade": evidence_grade,
                "occurrence_count": occurrence_count,
                "observed_at": item.get("observed_at"),
                "region": item.get("region"),
            },
        ))
    entries.extend(
        (
            raw,
            "provided_seed",
            f"seed:{index}",
            {"source_ref": f"seed:{index}", "source_kind": "provided_seed", "evidence_grade": "provided_seed"},
        )
        for index, raw in enumerate(payload.get("seed_questions", []), start=1)
    )
    for raw, source_kind, source_ref, provenance in entries:
        question = normalize_question(str(raw))
        key = question_dedupe_sha256(question) if question else ""
        if not question or key in seen:
            continue
        seen.add(key)
        unique.append((question, source_kind, source_ref, provenance))
    questions = []
    target_names = tuple(str(value).strip() for value in payload.get("target_names", []) if str(value).strip())
    competitor_names = tuple(str(value).strip() for value in payload.get("competitor_names", []) if str(value).strip())
    regions = tuple(str(value).strip() for value in payload.get("regions", []) if str(value).strip())
    for question, source_kind, source_ref, provenance in unique:
        governed = govern_question(
            question,
            target_names=target_names,
            competitor_names=competitor_names,
            regions=regions,
            source_kind=source_kind,  # type: ignore[arg-type]
            source_ref=source_ref,
        )
        questions.append({
            **governed.as_dict(),
            "source": source_kind,
            "version": governed.question_version_id,
            "provenance_records": [provenance],
        })
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


PAGE_BLUEPRINT_VERSION = "1.1.0"
PAGE_BLUEPRINT_ASSET_TYPES = {
    "fact_page",
    "product_page",
    "faq",
    "comparison_page",
    "case_page",
    "research_page",
    "json_ld",
    "llms_txt",
}
PAGE_BLUEPRINT_ASSET_LABELS = {
    "fact_page": "企业事实证据页",
    "product_page": "产品事实证据页",
    "faq": "事实问答页",
    "comparison_page": "证据比较页",
    "case_page": "案例证据页",
    "research_page": "研究证据页",
    "json_ld": "结构化事实数据",
    "llms_txt": "机器可读事实索引",
}


def _exact_blueprint_evidence(item: object, fact_text: str) -> bool:
    if not isinstance(item, dict):
        return False
    quoted_text = str(item.get("quoted_text") or "")
    try:
        source_start = int(item.get("source_start"))
        source_end = int(item.get("source_end"))
    except (TypeError, ValueError):
        return False
    source_sha256 = str(item.get("source_sha256") or "")
    return (
        quoted_text == fact_text
        and source_start >= 0
        and source_end - source_start == len(quoted_text)
        and bool(re.fullmatch(r"[0-9a-f]{64}", source_sha256))
        and bool(str(item.get("source_id") or "").strip())
    )


def _blueprint_missing_reasons(fact: dict[str, Any], now: datetime) -> list[str]:
    reasons: list[str] = []
    fact_text = str(fact.get("fact_text") or "").strip()
    if fact.get("status") != "approved":
        reasons.append("fact_not_approved")
    if fact.get("eligible_for_generation") is not True:
        reasons.append("fact_not_eligible")
    if fact.get("conflict_status", "none") == "open":
        reasons.append("open_conflict")
    if not fact_text or not str(fact.get("revision_id") or "").strip():
        reasons.append("fact_identity_or_text_missing")
    if not fact.get("support_ids"):
        reasons.append("claim_support_missing")
    valid_until = fact.get("valid_until")
    if valid_until:
        try:
            expires_at = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                reasons.append("fact_expired")
        except ValueError:
            reasons.append("fact_validity_invalid")
    evidence = fact.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        reasons.append("source_evidence_missing")
    else:
        if not any(_exact_blueprint_evidence(item, fact_text) for item in evidence):
            reasons.append("exact_source_boundary_missing")
    return reasons


def page_blueprint(payload: dict[str, Any]) -> dict[str, Any]:
    facts = [fact for fact in payload.get("facts", []) if isinstance(fact, dict)]
    asset_type = str(payload.get("asset_type") or "fact_page").strip()
    requested_title = str(payload.get("title") or "").strip()
    direction = str(payload.get("direction") or "").strip()
    now = datetime.now(timezone.utc)
    missing_evidence = []
    if asset_type not in PAGE_BLUEPRINT_ASSET_TYPES:
        missing_evidence.append(
            {"fact_id": None, "revision_id": None, "reasons": ["asset_type_unsupported"]}
        )
    if not requested_title:
        missing_evidence.append(
            {"fact_id": None, "revision_id": None, "reasons": ["title_missing"]}
        )
    for fact in facts:
        reasons = _blueprint_missing_reasons(fact, now)
        if reasons:
            missing_evidence.append(
                {
                    "fact_id": fact.get("fact_id"),
                    "revision_id": fact.get("revision_id"),
                    "reasons": reasons,
                }
            )
    if not facts or missing_evidence:
        return {
            "skill_id": "intervention.page-blueprint",
            "skill_version": PAGE_BLUEPRINT_VERSION,
            "status": "needs_evidence",
            "asset_type": asset_type,
            "title": requested_title,
            "missing_fact_ids": [
                item.get("fact_id") for item in missing_evidence if item.get("fact_id")
            ],
            "missing_evidence": missing_evidence,
            "sections": [],
            "claim_bindings": [],
            "structured_data": None,
            "body_md": "",
        }

    fact_title = re.sub(r"\s+", " ", str(facts[0].get("title") or "已核验事实")).strip()
    public_title = f"{fact_title[:120]}｜{PAGE_BLUEPRINT_ASSET_LABELS[asset_type]}"
    fact_ids = [str(fact["fact_id"]) for fact in facts]
    revision_ids = [str(fact["revision_id"]) for fact in facts]
    support_ids = sorted(
        {str(support_id) for fact in facts for support_id in fact.get("support_ids", [])}
    )
    claim_bindings = []
    evidence_lines = []
    for fact in facts:
        evidence = next(
            item
            for item in fact["evidence"]
            if _exact_blueprint_evidence(item, str(fact["fact_text"]).strip())
        )
        claim_bindings.append(
            {
                "claim_text": str(fact["fact_text"]).strip(),
                "claim_sha256": sha256_text(str(fact["fact_text"]).strip()),
                "fact_id": str(fact["fact_id"]),
                "fact_revision_id": str(fact["revision_id"]),
                "support_ids": sorted(str(item) for item in fact["support_ids"]),
                "source_id": str(evidence["source_id"]),
                "source_sha256": str(evidence["source_sha256"]),
                "source_start": int(evidence["source_start"]),
                "source_end": int(evidence["source_end"]),
            }
        )
        evidence_lines.append(
            f"- `[Evidence:{evidence['source_id']}:{evidence['source_start']}-{evidence['source_end']}:{evidence['source_sha256']}]`"
        )

    summary = "本页面仅编排已审核、仍有效且具有精确原文边界的企业事实。"
    sections = [
        {
            "section_id": "summary",
            "section_type": "summary",
            "heading": "证据范围",
            "body_md": summary,
            "fact_ids": fact_ids,
            "fact_revision_ids": revision_ids,
            "support_ids": support_ids,
        }
    ]
    for index, fact in enumerate(facts, start=1):
        sections.append(
            {
                "section_id": f"fact-{index}",
                "section_type": "fact",
                "heading": str(fact.get("title") or f"已核验事实 {index}"),
                "body_md": str(fact["fact_text"]).strip(),
                "fact_ids": [str(fact["fact_id"])],
                "fact_revision_ids": [str(fact["revision_id"])],
                "support_ids": sorted(str(item) for item in fact["support_ids"]),
            }
        )
    sections.append(
        {
            "section_id": "evidence-index",
            "section_type": "evidence",
            "heading": "证据索引",
            "body_md": "\n".join(evidence_lines),
            "fact_ids": fact_ids,
            "fact_revision_ids": revision_ids,
            "support_ids": support_ids,
        }
    )
    faq_entities = [
        {
            "@type": "Question",
            "name": f"关于{str(fact.get('title') or f'事实 {index}')}可以确认什么？",
            "acceptedAnswer": {
                "@type": "Answer",
                "text": str(fact["fact_text"]).strip(),
            },
        }
        for index, fact in enumerate(facts, start=1)
    ]
    structured_data: Any = {
        "@context": "https://schema.org",
        "@type": "FAQPage" if asset_type == "faq" else "WebPage",
        "name": public_title,
        "mainEntity": faq_entities,
    }
    if asset_type == "faq":
        sections.append(
            {
                "section_id": "faq",
                "section_type": "faq",
                "heading": "常见问题",
                "body_md": "\n\n".join(
                    f"### {item['name']}\n\n{item['acceptedAnswer']['text']}" for item in faq_entities
                ),
                "fact_ids": fact_ids,
                "fact_revision_ids": revision_ids,
                "support_ids": support_ids,
            }
        )

    if asset_type == "json_ld":
        body_md = "```json\n" + json.dumps(structured_data, ensure_ascii=False, indent=2) + "\n```"
    elif asset_type == "llms_txt":
        body_md = "\n".join(
            [f"# {public_title}", summary, "", "## Verified facts"]
            + [f"- {fact['fact_text']} [FactRevision:{fact['revision_id']}]" for fact in facts]
            + ["", "## Evidence"]
            + evidence_lines
        )
        structured_data = None
    else:
        body_lines = [f"# {public_title}", "", f"> {summary}"]
        for section in sections[1:]:
            body_lines.extend(["", f"## {section['heading']}", "", section["body_md"]])
            if section["section_type"] == "fact":
                body_lines.append(
                    f"`[FactRevision:{section['fact_revision_ids'][0]}]`"
                )
        body_lines.extend(["", "发布前仍须通过内容风险扫描与人工审核。"])
        body_md = "\n".join(body_lines)

    blueprint = {
        "skill_id": "intervention.page-blueprint",
        "skill_version": PAGE_BLUEPRINT_VERSION,
        "status": "draft",
        "asset_type": asset_type,
        "title": public_title,
        "editorial_brief_sha256": sha256_text(
            json.dumps(
                {"requested_title": requested_title, "direction": direction},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        "missing_fact_ids": [],
        "missing_evidence": [],
        "sections": sections,
        "claim_bindings": claim_bindings,
        "structured_data": structured_data,
        "body_md": body_md,
    }
    blueprint["blueprint_sha256"] = sha256_text(
        json.dumps(blueprint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return blueprint


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
