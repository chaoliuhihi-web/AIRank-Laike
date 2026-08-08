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
    if asset_type == "comparison_page":
        missing_evidence.append(
            {
                "fact_id": None,
                "revision_id": None,
                "reasons": ["comparison_builder_required"],
            }
        )
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


COMPARISON_BUILDER_VERSION = "1.0.0"
COMPARISON_SUBJECT_TYPES = {"brand", "company", "product", "competitor", "solution_type"}

EXPLAINER_BUILDER_VERSION = "1.0.0"
EXPLAINER_ROLE_MINIMUMS = {
    "definition": 1,
    "mechanism": 2,
    "step": 3,
    "criterion": 2,
    "misconception": 1,
    "faq": 2,
    "boundary": 1,
}
EXPLAINER_ROLE_LABELS = {
    "definition": "定义与范围",
    "mechanism": "工作机制",
    "step": "实施步骤",
    "criterion": "判断标准",
    "misconception": "常见误区",
    "faq": "常见问题",
    "boundary": "适用边界",
}


def explainer_builder(payload: dict[str, Any]) -> dict[str, Any]:
    requested_title = str(payload.get("title") or "").strip()
    direction = str(payload.get("direction") or "").strip()
    subject_id = str(payload.get("subject_id") or "").strip()
    subject_type = str(payload.get("subject_type") or "").strip()
    display_name = str(payload.get("display_name") or "").strip()
    brand_names = [str(item).strip() for item in payload.get("brand_names", []) if str(item).strip()]
    facts = [item for item in payload.get("facts", []) if isinstance(item, dict)]
    now = datetime.now(timezone.utc)
    missing_evidence: list[dict[str, Any]] = []
    if not requested_title:
        missing_evidence.append({"content_role": None, "fact_id": None, "reasons": ["title_missing"]})
    if not subject_id or subject_type not in COMPARISON_SUBJECT_TYPES or not display_name:
        missing_evidence.append({"content_role": None, "fact_id": None, "reasons": ["subject_definition_invalid"]})
    normalized_brand_names = list(dict.fromkeys([display_name, *brand_names]))
    facts_by_role: dict[str, list[dict[str, Any]]] = {role: [] for role in EXPLAINER_ROLE_MINIMUMS}
    seen_revisions: set[str] = set()
    for fact in facts:
        content_role = str(fact.get("content_role") or "").strip()
        revision_id = str(fact.get("revision_id") or "").strip()
        reasons = _blueprint_missing_reasons(fact, now)
        if content_role not in EXPLAINER_ROLE_MINIMUMS:
            reasons.append("content_role_unsupported")
        if (
            str(fact.get("subject_ref_id") or "").strip() != subject_id
            or str(fact.get("subject_type") or "").strip() != subject_type
        ):
            reasons.append("fact_subject_binding_mismatch")
        if revision_id in seen_revisions:
            reasons.append("fact_revision_reused_across_roles")
        seen_revisions.add(revision_id)
        if reasons:
            missing_evidence.append(
                {
                    "content_role": content_role or None,
                    "fact_id": fact.get("fact_id"),
                    "revision_id": revision_id or None,
                    "reasons": list(dict.fromkeys(reasons)),
                }
            )
            continue
        facts_by_role[content_role].append(fact)

    role_coverage = {}
    for role, minimum in EXPLAINER_ROLE_MINIMUMS.items():
        actual = len(facts_by_role[role])
        role_coverage[role] = {"required": minimum, "actual": actual, "complete": actual >= minimum}
        if actual < minimum:
            missing_evidence.append(
                {"content_role": role, "fact_id": None, "reasons": ["role_evidence_minimum_not_met"]}
            )

    accepted_facts = [fact for role_facts in facts_by_role.values() for fact in role_facts]
    supported_character_count = len(re.sub(r"\s+", "", "".join(str(fact.get("fact_text") or "") for fact in accepted_facts)))
    if supported_character_count < 1400:
        missing_evidence.append(
            {"content_role": None, "fact_id": None, "reasons": ["minimum_1400_supported_characters_required"]}
        )
    brand_mention_count = sum(
        str(fact.get("fact_text") or "").lower().count(name.lower())
        for fact in accepted_facts
        for name in normalized_brand_names
        if name
    )
    if brand_mention_count > 3:
        missing_evidence.append(
            {"content_role": None, "fact_id": None, "reasons": ["brand_mention_limit_exceeded"]}
        )

    quality = {
        "required_fact_count": sum(EXPLAINER_ROLE_MINIMUMS.values()),
        "accepted_fact_count": sum(len(items) for items in facts_by_role.values()),
        "supported_character_count": supported_character_count,
        "minimum_supported_character_count": 1400,
        "brand_mention_count": brand_mention_count,
        "brand_mention_limit": 3,
        "role_coverage": role_coverage,
        "all_claims_evidence_bound": not missing_evidence,
    }
    if missing_evidence:
        return {
            "skill_id": "intervention.explainer-builder",
            "skill_version": EXPLAINER_BUILDER_VERSION,
            "status": "needs_evidence",
            "asset_type": "explainer_page",
            "title": requested_title,
            "subject_id": subject_id,
            "subject_type": subject_type,
            "display_name": display_name,
            "quality": quality,
            "missing_evidence": missing_evidence,
            "sections": [],
            "claim_bindings": [],
            "source_ledger": [],
            "structured_data": None,
            "body_md": "",
        }

    public_title = f"{display_name}｜证据解释指南"
    sections: list[dict[str, Any]] = []
    claim_bindings: list[dict[str, Any]] = []
    source_ledger: list[dict[str, Any]] = []
    for role in EXPLAINER_ROLE_MINIMUMS:
        role_facts = facts_by_role[role]
        lines: list[str] = []
        for index, fact in enumerate(role_facts, start=1):
            fact_text = str(fact["fact_text"]).strip()
            evidence = next(item for item in fact["evidence"] if _exact_blueprint_evidence(item, fact_text))
            binding = {
                "claim_text": fact_text,
                "claim_sha256": sha256_text(fact_text),
                "fact_id": str(fact["fact_id"]),
                "fact_revision_id": str(fact["revision_id"]),
                "subject_id": subject_id,
                "content_role": role,
                "support_ids": sorted(str(item) for item in fact["support_ids"]),
                "source_id": str(evidence["source_id"]),
                "source_sha256": str(evidence["source_sha256"]),
                "source_start": int(evidence["source_start"]),
                "source_end": int(evidence["source_end"]),
            }
            claim_bindings.append(binding)
            source_ledger.append(
                {
                    "source_id": binding["source_id"],
                    "source_sha256": binding["source_sha256"],
                    "source_start": binding["source_start"],
                    "source_end": binding["source_end"],
                    "fact_revision_id": binding["fact_revision_id"],
                    "content_role": role,
                }
            )
            prefix = f"### 步骤 {index}" if role == "step" else f"### 证据说明 {index}"
            lines.extend([prefix, fact_text, f"`[FactRevision:{fact['revision_id']}]`"])
        sections.append(
            {
                "section_id": f"role-{role}",
                "section_type": role,
                "heading": EXPLAINER_ROLE_LABELS[role],
                "body_md": "\n\n".join(lines),
                "fact_revision_ids": [str(item["revision_id"]) for item in role_facts],
                "support_ids": sorted({str(support_id) for item in role_facts for support_id in item["support_ids"]}),
            }
        )

    faq_facts = facts_by_role["faq"]
    step_facts = facts_by_role["step"]
    structured_data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "HowTo",
                "name": public_title,
                "step": [
                    {"@type": "HowToStep", "position": index, "text": str(fact["fact_text"]).strip()}
                    for index, fact in enumerate(step_facts, start=1)
                ],
            },
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": str(fact.get("title") or f"证据问题 {index}"),
                        "acceptedAnswer": {"@type": "Answer", "text": str(fact["fact_text"]).strip()},
                    }
                    for index, fact in enumerate(faq_facts, start=1)
                ],
            },
        ],
    }
    body_lines = [
        f"# {public_title}",
        "",
        "> 本指南只编排已审核、仍有效且有精确来源边界的事实。缺少证据的解释不会进入正文。",
    ]
    for section in sections:
        body_lines.extend(["", f"## {section['heading']}", "", section["body_md"]])
    explainer = {
        "skill_id": "intervention.explainer-builder",
        "skill_version": EXPLAINER_BUILDER_VERSION,
        "status": "draft",
        "asset_type": "explainer_page",
        "title": public_title,
        "subject_id": subject_id,
        "subject_type": subject_type,
        "display_name": display_name,
        "editorial_brief_sha256": sha256_text(
            json.dumps(
                {"requested_title": requested_title, "direction": direction},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        "quality": quality,
        "missing_evidence": [],
        "sections": sections,
        "claim_bindings": claim_bindings,
        "source_ledger": source_ledger,
        "structured_data": structured_data,
        "body_md": "\n".join(body_lines),
    }
    explainer["blueprint_sha256"] = sha256_text(
        json.dumps(explainer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return explainer


def comparison_builder(payload: dict[str, Any]) -> dict[str, Any]:
    requested_title = str(payload.get("title") or "").strip()
    direction = str(payload.get("direction") or "").strip()
    target_subject_id = str(payload.get("target_subject_id") or "").strip()
    subjects = [item for item in payload.get("subjects", []) if isinstance(item, dict)]
    dimensions = [item for item in payload.get("dimensions", []) if isinstance(item, dict)]
    facts = [item for item in payload.get("facts", []) if isinstance(item, dict)]
    now = datetime.now(timezone.utc)
    missing_evidence: list[dict[str, Any]] = []

    subject_by_id: dict[str, dict[str, Any]] = {}
    for item in subjects:
        subject_id = str(item.get("subject_id") or "").strip()
        subject_type = str(item.get("subject_type") or "").strip()
        display_name = str(item.get("display_name") or "").strip()
        if not subject_id or subject_id in subject_by_id or not display_name or subject_type not in COMPARISON_SUBJECT_TYPES:
            missing_evidence.append(
                {
                    "subject_id": subject_id or None,
                    "dimension_id": None,
                    "reasons": ["subject_definition_invalid_or_duplicate"],
                }
            )
            continue
        subject_by_id[subject_id] = {
            "subject_id": subject_id,
            "subject_type": subject_type,
            "display_name": display_name,
        }
    if not 2 <= len(subject_by_id) <= 4:
        missing_evidence.append(
            {"subject_id": None, "dimension_id": None, "reasons": ["subject_count_must_be_2_to_4"]}
        )
    if target_subject_id not in subject_by_id:
        missing_evidence.append(
            {"subject_id": target_subject_id or None, "dimension_id": None, "reasons": ["target_subject_missing"]}
        )

    dimension_by_id: dict[str, dict[str, str]] = {}
    for item in dimensions:
        dimension_id = str(item.get("dimension_id") or "").strip()
        label = str(item.get("label") or "").strip()
        if not dimension_id or dimension_id in dimension_by_id or not label:
            missing_evidence.append(
                {
                    "subject_id": None,
                    "dimension_id": dimension_id or None,
                    "reasons": ["dimension_definition_invalid_or_duplicate"],
                }
            )
            continue
        dimension_by_id[dimension_id] = {"dimension_id": dimension_id, "label": label}
    if len(dimension_by_id) < 10:
        missing_evidence.append(
            {"subject_id": None, "dimension_id": None, "reasons": ["minimum_10_dimensions_required"]}
        )
    if not requested_title:
        missing_evidence.append(
            {"subject_id": None, "dimension_id": None, "reasons": ["title_missing"]}
        )

    facts_by_cell: dict[tuple[str, str], list[dict[str, Any]]] = {}
    seen_revisions: set[str] = set()
    for fact in facts:
        subject_id = str(fact.get("subject_id") or "").strip()
        dimension_id = str(fact.get("dimension_id") or "").strip()
        revision_id = str(fact.get("revision_id") or "").strip()
        reasons = _blueprint_missing_reasons(fact, now)
        declared_subject = subject_by_id.get(subject_id)
        if declared_subject is None:
            reasons.append("fact_subject_not_declared")
        elif (
            str(fact.get("subject_ref_id") or "").strip() != subject_id
            or str(fact.get("subject_type") or "").strip() != declared_subject["subject_type"]
        ):
            reasons.append("fact_subject_binding_mismatch")
        if dimension_id not in dimension_by_id:
            reasons.append("fact_dimension_not_declared")
        if revision_id in seen_revisions:
            reasons.append("fact_revision_reused_across_cells")
        seen_revisions.add(revision_id)
        if reasons:
            missing_evidence.append(
                {
                    "subject_id": subject_id or None,
                    "dimension_id": dimension_id or None,
                    "fact_id": fact.get("fact_id"),
                    "revision_id": revision_id or None,
                    "reasons": list(dict.fromkeys(reasons)),
                }
            )
            continue
        facts_by_cell.setdefault((subject_id, dimension_id), []).append(fact)

    for subject_id in subject_by_id:
        for dimension_id in dimension_by_id:
            if not facts_by_cell.get((subject_id, dimension_id)):
                missing_evidence.append(
                    {
                        "subject_id": subject_id,
                        "dimension_id": dimension_id,
                        "reasons": ["symmetric_evidence_cell_missing"],
                    }
                )

    coverage_total = len(subject_by_id) * len(dimension_by_id)
    coverage_complete = sum(bool(facts_by_cell.get((subject_id, dimension_id))) for subject_id in subject_by_id for dimension_id in dimension_by_id)
    fairness = {
        "same_scope": coverage_total > 0 and coverage_complete == coverage_total,
        "subject_count": len(subject_by_id),
        "dimension_count": len(dimension_by_id),
        "required_cell_count": coverage_total,
        "covered_cell_count": coverage_complete,
        "coverage_rate": round(coverage_complete / coverage_total, 6) if coverage_total else 0.0,
        "ranking_or_score_generated": False,
    }
    if missing_evidence:
        return {
            "skill_id": "intervention.comparison-builder",
            "skill_version": COMPARISON_BUILDER_VERSION,
            "status": "needs_evidence",
            "asset_type": "comparison_page",
            "title": requested_title,
            "target_subject_id": target_subject_id,
            "subjects": list(subject_by_id.values()),
            "dimensions": list(dimension_by_id.values()),
            "fairness": fairness,
            "missing_evidence": missing_evidence,
            "sections": [],
            "claim_bindings": [],
            "source_ledger": [],
            "body_md": "",
        }

    ordered_subjects = list(subject_by_id.values())
    public_title = "、".join(item["display_name"] for item in ordered_subjects) + "｜同维度证据对比"
    claim_bindings: list[dict[str, Any]] = []
    source_ledger: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    for dimension in dimension_by_id.values():
        section_facts: list[dict[str, Any]] = []
        section_lines: list[str] = []
        for subject in ordered_subjects:
            cell_facts = facts_by_cell[(subject["subject_id"], dimension["dimension_id"])]
            section_lines.append(f"### {subject['display_name']}")
            for fact in cell_facts:
                fact_text = str(fact["fact_text"]).strip()
                evidence = next(item for item in fact["evidence"] if _exact_blueprint_evidence(item, fact_text))
                binding = {
                    "claim_text": fact_text,
                    "claim_sha256": sha256_text(fact_text),
                    "fact_id": str(fact["fact_id"]),
                    "fact_revision_id": str(fact["revision_id"]),
                    "subject_id": subject["subject_id"],
                    "dimension_id": dimension["dimension_id"],
                    "support_ids": sorted(str(item) for item in fact["support_ids"]),
                    "source_id": str(evidence["source_id"]),
                    "source_sha256": str(evidence["source_sha256"]),
                    "source_start": int(evidence["source_start"]),
                    "source_end": int(evidence["source_end"]),
                }
                claim_bindings.append(binding)
                source_ledger.append(
                    {
                        "source_id": binding["source_id"],
                        "source_sha256": binding["source_sha256"],
                        "source_start": binding["source_start"],
                        "source_end": binding["source_end"],
                        "fact_revision_id": binding["fact_revision_id"],
                        "subject_id": subject["subject_id"],
                        "dimension_id": dimension["dimension_id"],
                    }
                )
                section_lines.extend([fact_text, f"`[FactRevision:{fact['revision_id']}]`"])
                section_facts.append(fact)
        sections.append(
            {
                "section_id": f"dimension-{dimension['dimension_id']}",
                "section_type": "comparison_dimension",
                "heading": dimension["label"],
                "body_md": "\n\n".join(section_lines),
                "subject_ids": [item["subject_id"] for item in ordered_subjects],
                "fact_revision_ids": [str(item["revision_id"]) for item in section_facts],
                "support_ids": sorted({str(support_id) for item in section_facts for support_id in item["support_ids"]}),
            }
        )

    body_lines = [
        f"# {public_title}",
        "",
        "> 本报告按相同维度展示已审核、仍有效且具有精确来源边界的事实；不生成排名、分数或无证据优劣结论。",
    ]
    for section in sections:
        body_lines.extend(["", f"## {section['heading']}", "", section["body_md"]])
    body_lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "这些事实只能说明已核验范围内的差异。选型仍需结合预算、部署边界、服务范围和采购约束逐项复核。",
        ]
    )
    comparison = {
        "skill_id": "intervention.comparison-builder",
        "skill_version": COMPARISON_BUILDER_VERSION,
        "status": "draft",
        "asset_type": "comparison_page",
        "title": public_title,
        "target_subject_id": target_subject_id,
        "subjects": ordered_subjects,
        "dimensions": list(dimension_by_id.values()),
        "editorial_brief_sha256": sha256_text(
            json.dumps(
                {"requested_title": requested_title, "direction": direction},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        "fairness": fairness,
        "missing_evidence": [],
        "sections": sections,
        "claim_bindings": claim_bindings,
        "source_ledger": source_ledger,
        "body_md": "\n".join(body_lines),
    }
    comparison["blueprint_sha256"] = sha256_text(
        json.dumps(comparison, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return comparison


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
    "intervention.explainer-builder": explainer_builder,
    "intervention.comparison-builder": comparison_builder,
    "delivery.retest-report": retest_report,
}


def run_skill(skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        runner = SKILL_RUNNERS[skill_id]
    except KeyError as exc:
        raise KeyError(f"unknown AIRank skill runner: {skill_id}") from exc
    return runner(payload)
