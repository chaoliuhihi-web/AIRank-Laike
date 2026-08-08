from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_content_gap_actions_require_quality_gated_immutable_evidence() -> None:
    route_source = (ROOT / "apps" / "api" / "evidence_gap_routes.py").read_text(
        encoding="utf-8"
    )
    asset_source = (ROOT / "apps" / "api" / "main.py").read_text(encoding="utf-8")

    for required in (
        'GAP_CONTRACT_VERSION = "airank.evidence-gap.v2"',
        'DERIVATION_POLICY = "airank.brand-unmentioned-gap.v1"',
        'quality.get("publishable") is not True',
        'item.sample_status == "valid"',
        'item.mention_class == "not_mentioned"',
        "len(independent_sessions) != repetitions",
        "answer_snapshot_ids",
        "evidence_snapshot_ids",
        "quality_report_sha256",
        "evidence_basis_sha256",
    ):
        assert required in route_source

    assert "contract_version = 'airank.evidence-gap.v2'" in asset_source
    assert "AND evidence_sha256 IS NOT NULL" in asset_source
    assert "未绑定样本证据的历史缺口" in asset_source


def test_web_exposes_real_derivation_and_never_promises_recommendation() -> None:
    web_source = (ROOT / "apps" / "web" / "src" / "App.tsx").read_text(
        encoding="utf-8"
    )

    assert 'data-testid="evidence-gap-derive-form"' in web_source
    assert "从真实样本推导" in web_source
    assert "未提及仍计入有效分母" in web_source
    assert "不代表发布内容后必然获得推荐" in (
        ROOT / "apps" / "api" / "evidence_gap_routes.py"
    ).read_text(encoding="utf-8")

