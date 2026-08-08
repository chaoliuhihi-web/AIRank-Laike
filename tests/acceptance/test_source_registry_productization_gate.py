from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_source_registry_is_versioned_human_evidence_not_inferred_authority() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "20260808_0020_source_registry.py"
    ).read_text(encoding="utf-8")
    routes = (ROOT / "apps" / "api" / "source_registry_routes.py").read_text(
        encoding="utf-8"
    )

    for field in (
        "normalized_host",
        "revision_number",
        "classification_status",
        "classification_method",
        "classification_confidence",
        "authority_level",
        "usage_policy",
        "risk_level",
        "evidence_note",
        "supersedes_revision_id",
        "request_sha256",
    ):
        assert field in migration
    assert "unclassified" in routes
    assert "human_review" in routes
    assert "dataset_import" in routes
    assert "SOURCE_CLASSIFICATION_VERSION_CONFLICT" in routes
    assert "classification_status=\"reviewed\"" in routes
    assert "authority_level=payload.authority_level" in routes
    assert "infer" not in routes.lower()
