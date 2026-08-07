from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_absorption_matrix.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_absorption_matrix", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_absorption_matrix_covers_every_source_and_geo_skill() -> None:
    result = load_verifier().validate()

    assert result["status"] == "pass", result["errors"]
    assert result["source_count"] == 12
    assert result["geo_skill_count"] == 21
    assert set(result["decisions"]) == {"absorb", "adapt", "reference_only", "reject"}
