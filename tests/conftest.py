from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_api_auth_only_for_isolated_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contract fixtures opt out explicitly; production defaults to required."""

    monkeypatch.setenv("AIRANK_API_AUTH_ENFORCEMENT", "disabled")
