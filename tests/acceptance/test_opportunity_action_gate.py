from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_opportunity_actions_require_ownership_sla_and_newer_verification() -> None:
    migration = (ROOT / "apps/api/alembic/versions/20260809_0034_opportunity_actions.py").read_text(encoding="utf-8")
    routes = (ROOT / "apps/api/opportunity_action_routes.py").read_text(encoding="utf-8")
    for required in (
        "airank_opportunity_actions",
        "airank_opportunity_action_events",
        "previous_event_sha256",
        "event_sha256",
        "assigned_to",
        "due_at",
        "effect_claim_allowed",
        "verification_basis_sha256",
    ):
        assert required in migration
    assert 'FINAL_STATUSES = {"verified_not_observed", "waived"}' in routes
    assert "verification_run_must_be_latest_complete_derivation" in routes
    assert "verification_run_opportunity_manifest_is_inconsistent" in routes
    assert "opportunity_still_present_in_verification_run" in routes
    assert '"effect_claim_allowed": False' in routes
    assert '"OPPORTUNITY_ACTION_OWNER_FORBIDDEN"' in routes


def test_all_clear_opportunity_snapshot_is_allowed_only_after_a_real_baseline() -> None:
    routes = (ROOT / "apps/api/opportunity_routes.py").read_text(encoding="utf-8")
    derivation_schema = (ROOT / "packages/contracts/opportunity_derivation_response.schema.json").read_text(encoding="utf-8")
    assert "if not candidates and previous is None" in routes
    assert '"opportunity_count": { "type": "integer", "minimum": 0 }' in derivation_schema
    assert '"minItems": 1' not in derivation_schema
