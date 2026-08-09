from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_measurement_completion_does_not_mutate_project_profile_version() -> None:
    main = (ROOT / "apps/api/main.py").read_text(encoding="utf-8")

    assert "SET status = 'active', updated_at = :now" not in main
    assert "FROM airank_project_profile_revisions pr" in main
    assert 'project_row["profile_updated_at"]' in main


def test_all_downstream_profile_scope_gates_use_profile_revisions() -> None:
    for relative_path in (
        "apps/api/evidence_gap_routes.py",
        "apps/api/retest_routes.py",
        "apps/api/delivery_routes.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "airank_project_profile_revisions" in source, relative_path
