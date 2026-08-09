from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_provider_credential_vault_has_encrypted_storage_and_no_plaintext_column() -> None:
    migration = read("apps/api/alembic/versions/20260809_0040_provider_credential_vault.py")
    implementation = read("apps/api/provider_credentials.py")
    requirements = read("apps/api/requirements-dev.txt")

    assert "secret_ciphertext" in migration
    assert "secret_nonce" in migration
    assert "secret_fingerprint" in migration
    assert "event_sequence BIGINT NOT NULL" in migration
    assert "credential_source" in migration
    assert "api_key VARCHAR" not in migration
    assert "plaintext" not in migration.lower()
    assert "SecretStr" in implementation
    assert "confirm_billable: Literal[True]" in implementation
    assert "credential_revoked_and_ciphertext_scrubbed" in implementation
    assert "cryptography>=49.0.0,<50.0.0" in requirements


def test_provider_credential_contracts_never_expose_envelope_fields() -> None:
    response_schema = read("packages/contracts/provider_credential_response.schema.json")
    portfolio_schema = read("packages/contracts/provider_credential_portfolio_response.schema.json")
    api_client = read("apps/web/src/console/api.ts")
    console = read("apps/web/src/App.tsx")

    for forbidden in ("secret_ciphertext", "secret_nonce", "api_key"):
        assert forbidden not in response_schema
        assert forbidden not in portfolio_schema
    assert "fetchProviderCredentials" in api_client
    assert "upsertProviderCredential" in api_client
    assert "revokeProviderCredential" in api_client
    assert 'type="password"' in console
    assert 'autoComplete="new-password"' in console
    assert "L3 真实生成" in console
    assert "撤销并擦除" in console
