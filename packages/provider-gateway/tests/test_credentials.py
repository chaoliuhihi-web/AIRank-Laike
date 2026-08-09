from __future__ import annotations

import base64

import pytest

from airank_provider_gateway import CredentialKeyring, CredentialVaultError


def keyring() -> CredentialKeyring:
    return CredentialKeyring(
        active_encryption_key_id="enc-v1",
        encryption_keys={"enc-v1": b"e" * 32},
        active_fingerprint_key_id="fp-v1",
        fingerprint_keys={"fp-v1": b"f" * 32},
    )


def encrypt(ring: CredentialKeyring, credential_id: str, version: int, secret: str = "sk-private-provider-value"):
    return ring.encrypt(
        tenant_id="tenant_1",
        provider="qianwen",
        route_id="qianwen:default",
        credential_id=credential_id,
        credential_version=version,
        plaintext=secret,
    )


def test_aes_gcm_envelope_is_random_bound_to_scope_and_not_repr_leaky() -> None:
    ring = keyring()
    first = encrypt(ring, "credential_1", 1)
    second = encrypt(ring, "credential_2", 2)

    assert first.ciphertext != second.ciphertext
    assert first.nonce != second.nonce
    assert first.secret_fingerprint == second.secret_fingerprint
    assert first.secret_mask != "sk-private-provider-value"
    assert first.ciphertext not in repr(first)
    assert first.nonce not in repr(first)
    assert ring.decrypt(
        tenant_id="tenant_1",
        provider="qianwen",
        route_id="qianwen:default",
        credential_id="credential_1",
        credential_version=1,
        envelope=first,
    ) == "sk-private-provider-value"

    with pytest.raises(CredentialVaultError) as captured:
        ring.decrypt(
            tenant_id="tenant_2",
            provider="qianwen",
            route_id="qianwen:default",
            credential_id="credential_1",
            credential_version=1,
            envelope=first,
        )
    assert captured.value.code == "CREDENTIAL_DECRYPTION_FAILED"


def test_keyring_env_requires_distinct_exact_256_bit_base64_keys() -> None:
    environment = {
        "AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID": "enc-v1",
        "AIRANK_CREDENTIAL_ENCRYPTION_KEYS": '{"enc-v1":"' + base64.b64encode(b"e" * 32).decode() + '"}',
        "AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID": "fp-v1",
        "AIRANK_CREDENTIAL_FINGERPRINT_KEYS": '{"fp-v1":"' + base64.b64encode(b"f" * 32).decode() + '"}',
    }
    assert CredentialKeyring.from_env(environment).active_encryption_key_id == "enc-v1"

    environment["AIRANK_CREDENTIAL_FINGERPRINT_KEYS"] = environment[
        "AIRANK_CREDENTIAL_ENCRYPTION_KEYS"
    ].replace("enc-v1", "fp-v1")
    with pytest.raises(CredentialVaultError) as captured:
        CredentialKeyring.from_env(environment)
    assert captured.value.code == "CREDENTIAL_KEY_DOMAIN_REUSE"


def test_ciphertext_tampering_fails_without_exposing_secret() -> None:
    ring = keyring()
    envelope = encrypt(ring, "credential_1", 1)
    tampered = envelope.__class__(
        ciphertext=envelope.ciphertext[:-2] + "AA",
        nonce=envelope.nonce,
        secret_mask=envelope.secret_mask,
        secret_fingerprint=envelope.secret_fingerprint,
        encryption_key_id=envelope.encryption_key_id,
        fingerprint_key_id=envelope.fingerprint_key_id,
        algorithm=envelope.algorithm,
    )
    with pytest.raises(CredentialVaultError) as captured:
        ring.decrypt(
            tenant_id="tenant_1",
            provider="qianwen",
            route_id="qianwen:default",
            credential_id="credential_1",
            credential_version=1,
            envelope=tampered,
        )
    assert captured.value.code == "CREDENTIAL_DECRYPTION_FAILED"
    assert "sk-private-provider-value" not in str(captured.value)


def test_fingerprint_match_survives_active_fingerprint_key_rotation() -> None:
    original = keyring()
    old_envelope = encrypt(
        original,
        "credential_1",
        1,
        "sk-same-secret-after-key-rotation",
    )
    rotated = CredentialKeyring(
        active_encryption_key_id="enc-v2",
        encryption_keys={"enc-v1": b"e" * 32, "enc-v2": b"n" * 32},
        active_fingerprint_key_id="fp-v2",
        fingerprint_keys={"fp-v1": b"f" * 32, "fp-v2": b"g" * 32},
    )
    new_envelope = encrypt(
        rotated,
        "credential_2",
        2,
        "sk-same-secret-after-key-rotation",
    )

    assert new_envelope.secret_fingerprint != old_envelope.secret_fingerprint
    assert rotated.matches_fingerprint(
        tenant_id="tenant_1",
        provider="qianwen",
        route_id="qianwen:default",
        plaintext="sk-same-secret-after-key-rotation",
        expected_fingerprint=old_envelope.secret_fingerprint,
        fingerprint_key_id="fp-v1",
    )
