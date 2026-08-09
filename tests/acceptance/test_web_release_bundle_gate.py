from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_vite_release_build_has_stable_dependency_chunks() -> None:
    config = (ROOT / "apps/web/vite.config.ts").read_text(encoding="utf-8")

    assert "manualChunks" in config
    assert 'return "react-vendor"' in config
    assert 'return "icons-vendor"' in config
    assert 'return "console-api"' in config
    assert "sourcemap: false" in config


def test_release_bundle_budget_is_enforced_in_ci() -> None:
    package = (ROOT / "apps/web/package.json").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert '"check:bundle"' in package
    assert "npm run check:bundle" in workflow
