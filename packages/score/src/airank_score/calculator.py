from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


WEIGHTS: dict[str, int] = {
    "brand_mention": 20,
    "recommendation_rank": 20,
    "citation_coverage": 15,
    "competitor_suppression": 15,
    "fact_consistency": 15,
    "purchase_intent_coverage": 10,
    "answer_stability": 5,
}


@dataclass(frozen=True)
class ScoreComponent:
    key: str
    label: str
    points: float
    max_points: int
    evidence_refs: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ScoreResult:
    snapshot_id: str
    total: float
    max_total: int
    components: tuple[ScoreComponent, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "total": self.total,
            "max_total": self.max_total,
            "components": [
                {
                    "key": component.key,
                    "label": component.label,
                    "points": component.points,
                    "max_points": component.max_points,
                    "evidence_refs": list(component.evidence_refs),
                    "reason": component.reason,
                }
                for component in self.components
            ],
        }


def calculate_airank_score(snapshot: Any) -> ScoreResult:
    """Calculate a deterministic score from one answer snapshot and citations."""

    snapshot_id = text_attr(snapshot, "id")
    citation_ids = tuple(sorted(citation_id_values(snapshot)))
    base_refs = (snapshot_id, *citation_ids)
    brand_mentioned = bool_attr(snapshot, "brand_mentioned")
    brand_rank = int_attr(snapshot, "brand_rank")

    components = (
        ScoreComponent(
            key="brand_mention",
            label="品牌提及率",
            points=float(WEIGHTS["brand_mention"] if brand_mentioned else 0),
            max_points=WEIGHTS["brand_mention"],
            evidence_refs=base_refs,
            reason="brand_mentioned=true" if brand_mentioned else "brand not mentioned in snapshot",
        ),
        ScoreComponent(
            key="recommendation_rank",
            label="推荐率",
            points=float(rank_points(brand_rank)),
            max_points=WEIGHTS["recommendation_rank"],
            evidence_refs=base_refs,
            reason=rank_reason(brand_rank),
        ),
        ScoreComponent(
            key="citation_coverage",
            label="引用率",
            points=float(citation_points(citation_ids)),
            max_points=WEIGHTS["citation_coverage"],
            evidence_refs=citation_ids,
            reason=f"{len(citation_ids)} citation(s) attached to snapshot",
        ),
        pending_component("competitor_suppression", "竞品压制程度", base_refs),
        pending_component("fact_consistency", "事实一致性", base_refs),
        pending_component("purchase_intent_coverage", "高购买意图覆盖", base_refs),
        pending_component("answer_stability", "答案稳定性", base_refs),
    )
    total = round(sum(component.points for component in components), 4)
    return ScoreResult(
        snapshot_id=snapshot_id,
        total=total,
        max_total=sum(WEIGHTS.values()),
        components=components,
    )


def pending_component(key: str, label: str, refs: tuple[str, ...]) -> ScoreComponent:
    return ScoreComponent(
        key=key,
        label=label,
        points=0.0,
        max_points=WEIGHTS[key],
        evidence_refs=refs,
        reason="pending_input",
    )


def rank_points(brand_rank: int | None) -> int:
    if brand_rank is None:
        return 0
    if brand_rank < 1:
        return 0
    if brand_rank == 1:
        return 20
    if brand_rank <= 3:
        return 15
    return 8


def rank_reason(brand_rank: int | None) -> str:
    if brand_rank is None:
        return "brand rank absent"
    if brand_rank < 1:
        return f"invalid brand_rank={brand_rank}"
    return f"brand_rank={brand_rank}"


def citation_points(citation_ids: tuple[str, ...]) -> float:
    if not citation_ids:
        return 0.0
    return min(float(WEIGHTS["citation_coverage"]), len(citation_ids) * 7.5)


def citation_id_values(snapshot: Any) -> Iterable[str]:
    citations = getattr(snapshot, "citations", None)
    if citations is None and isinstance(snapshot, dict):
        citations = snapshot.get("citations", ())
    for citation in citations or ():
        citation_id = text_attr(citation, "id")
        if citation_id:
            yield citation_id


def text_attr(value: Any, key: str) -> str:
    if isinstance(value, dict):
        raw = value.get(key)
    else:
        raw = getattr(value, key)
    return str(raw)


def bool_attr(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return bool(value.get(key))
    return bool(getattr(value, key))


def int_attr(value: Any, key: str) -> int | None:
    if isinstance(value, dict):
        raw = value.get(key)
    else:
        raw = getattr(value, key)
    if raw is None:
        return None
    return int(raw)
