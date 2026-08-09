from __future__ import annotations

from dataclasses import dataclass, field
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
from typing import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,63}$")
_ALGORITHM = "aes-256-gcm"
_CONTRACT = "airank.provider-credential-envelope.v1"


class CredentialVaultError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CredentialEnvelope:
    ciphertext: str = field(repr=False)
    nonce: str = field(repr=False)
    secret_mask: str
    secret_fingerprint: str
    encryption_key_id: str
    fingerprint_key_id: str
    algorithm: str = _ALGORITHM


class CredentialKeyring:
    """Versioned AEAD keyring with a separate HMAC fingerprint domain.

    Key material is injected by the deployment secret manager. Database rows
    contain only ciphertext, a random nonce, key identifiers, a mask and a
    keyed fingerprint. Tenant/provider/route/record/version are authenticated
    as AAD, so moving a ciphertext to another scope fails closed.
    """

    def __init__(
        self,
        *,
        active_encryption_key_id: str,
        encryption_keys: Mapping[str, bytes],
        active_fingerprint_key_id: str,
        fingerprint_keys: Mapping[str, bytes],
    ) -> None:
        self.active_encryption_key_id = _validate_key_id(active_encryption_key_id)
        self.active_fingerprint_key_id = _validate_key_id(active_fingerprint_key_id)
        self._encryption_keys = _validate_keys(encryption_keys, "encryption")
        self._fingerprint_keys = _validate_keys(fingerprint_keys, "fingerprint")
        if self.active_encryption_key_id not in self._encryption_keys:
            raise CredentialVaultError(
                "CREDENTIAL_ENCRYPTION_KEY_UNAVAILABLE",
                "active credential encryption key is unavailable",
            )
        if self.active_fingerprint_key_id not in self._fingerprint_keys:
            raise CredentialVaultError(
                "CREDENTIAL_FINGERPRINT_KEY_UNAVAILABLE",
                "active credential fingerprint key is unavailable",
            )
        encryption_material = {hashlib.sha256(value).digest() for value in self._encryption_keys.values()}
        fingerprint_material = {hashlib.sha256(value).digest() for value in self._fingerprint_keys.values()}
        if encryption_material.intersection(fingerprint_material):
            raise CredentialVaultError(
                "CREDENTIAL_KEY_DOMAIN_REUSE",
                "credential encryption and fingerprint keys must use different material",
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "CredentialKeyring":
        values = env if env is not None else os.environ
        return cls(
            active_encryption_key_id=str(
                values.get("AIRANK_CREDENTIAL_ACTIVE_ENCRYPTION_KEY_ID") or ""
            ).strip(),
            encryption_keys=_parse_key_map(
                values.get("AIRANK_CREDENTIAL_ENCRYPTION_KEYS"), "encryption"
            ),
            active_fingerprint_key_id=str(
                values.get("AIRANK_CREDENTIAL_ACTIVE_FINGERPRINT_KEY_ID") or ""
            ).strip(),
            fingerprint_keys=_parse_key_map(
                values.get("AIRANK_CREDENTIAL_FINGERPRINT_KEYS"), "fingerprint"
            ),
        )

    def encrypt(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        credential_id: str,
        credential_version: int,
        plaintext: str,
    ) -> CredentialEnvelope:
        secret = _validate_secret(plaintext)
        context = _credential_context(
            tenant_id, provider, route_id, credential_id, credential_version
        )
        nonce = os.urandom(12)
        cipher = AESGCM(self._encryption_keys[self.active_encryption_key_id])
        ciphertext = cipher.encrypt(nonce, secret.encode("utf-8"), context)
        fingerprint = self._fingerprint(
            tenant_id=tenant_id,
            provider=provider,
            route_id=route_id,
            plaintext=secret,
            fingerprint_key_id=self.active_fingerprint_key_id,
        )
        return CredentialEnvelope(
            ciphertext=base64.b64encode(ciphertext).decode("ascii"),
            nonce=base64.b64encode(nonce).decode("ascii"),
            secret_mask=mask_secret(secret),
            secret_fingerprint=fingerprint,
            encryption_key_id=self.active_encryption_key_id,
            fingerprint_key_id=self.active_fingerprint_key_id,
        )

    def decrypt(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        credential_id: str,
        credential_version: int,
        envelope: CredentialEnvelope,
    ) -> str:
        key = self._encryption_keys.get(envelope.encryption_key_id)
        if key is None:
            raise CredentialVaultError(
                "CREDENTIAL_ENCRYPTION_KEY_UNAVAILABLE",
                "credential encryption key is unavailable",
            )
        if envelope.algorithm != _ALGORITHM:
            raise CredentialVaultError(
                "CREDENTIAL_ALGORITHM_UNSUPPORTED",
                "credential encryption algorithm is unsupported",
            )
        try:
            nonce = base64.b64decode(envelope.nonce, validate=True)
            ciphertext = base64.b64decode(envelope.ciphertext, validate=True)
            context = _credential_context(
                tenant_id, provider, route_id, credential_id, credential_version
            )
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, context).decode("utf-8")
        except (InvalidTag, UnicodeDecodeError, ValueError, binascii.Error) as exc:
            raise CredentialVaultError(
                "CREDENTIAL_DECRYPTION_FAILED",
                "credential ciphertext failed authenticated decryption",
            ) from exc
        return _validate_secret(plaintext)

    def matches_fingerprint(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        plaintext: str,
        expected_fingerprint: str,
        fingerprint_key_id: str,
    ) -> bool:
        candidate = self._fingerprint(
            tenant_id=tenant_id,
            provider=provider,
            route_id=route_id,
            plaintext=plaintext,
            fingerprint_key_id=fingerprint_key_id,
        )
        return hmac.compare_digest(candidate, str(expected_fingerprint or ""))

    def fingerprint_secret(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        plaintext: str,
        fingerprint_key_id: str | None = None,
    ) -> tuple[str, str]:
        key_id = fingerprint_key_id or self.active_fingerprint_key_id
        return (
            self._fingerprint(
                tenant_id=tenant_id,
                provider=provider,
                route_id=route_id,
                plaintext=plaintext,
                fingerprint_key_id=key_id,
            ),
            key_id,
        )

    def _fingerprint(
        self,
        *,
        tenant_id: str,
        provider: str,
        route_id: str,
        plaintext: str,
        fingerprint_key_id: str,
    ) -> str:
        key = self._fingerprint_keys.get(fingerprint_key_id)
        if key is None:
            raise CredentialVaultError(
                "CREDENTIAL_FINGERPRINT_KEY_UNAVAILABLE",
                "credential fingerprint key is unavailable",
            )
        secret = _validate_secret(plaintext)
        context = _fingerprint_context(tenant_id, provider, route_id)
        return hmac.new(
            key,
            context + b"\x00" + secret.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


def mask_secret(secret: str) -> str:
    value = secret.strip()
    if len(value) <= 8:
        return "****" + value[-2:]
    if len(value) <= 14:
        return value[:2] + "****" + value[-3:]
    return value[:5] + "****" + value[-4:]


def _credential_context(
    tenant_id: str,
    provider: str,
    route_id: str,
    credential_id: str,
    credential_version: int,
) -> bytes:
    values = (
        _CONTRACT,
        tenant_id.strip(),
        provider.strip().lower(),
        route_id.strip(),
        credential_id.strip(),
        str(credential_version),
    )
    if any(not value for value in values) or credential_version < 1:
        raise CredentialVaultError(
            "CREDENTIAL_CONTEXT_INVALID", "credential encryption context is invalid"
        )
    return "\x00".join(values).encode("utf-8")


def _fingerprint_context(tenant_id: str, provider: str, route_id: str) -> bytes:
    values = (
        "airank.provider-credential-fingerprint.v1",
        tenant_id.strip(),
        provider.strip().lower(),
        route_id.strip(),
    )
    if any(not value for value in values):
        raise CredentialVaultError(
            "CREDENTIAL_CONTEXT_INVALID", "credential fingerprint context is invalid"
        )
    return "\x00".join(values).encode("utf-8")


def _validate_secret(value: str) -> str:
    secret = str(value or "").strip()
    if not 8 <= len(secret) <= 16_384 or any(character.isspace() for character in secret):
        raise CredentialVaultError(
            "CREDENTIAL_SECRET_INVALID",
            "credential must be 8-16384 non-whitespace characters",
        )
    return secret


def _validate_key_id(value: str) -> str:
    key_id = str(value or "").strip()
    if not _KEY_ID.fullmatch(key_id):
        raise CredentialVaultError(
            "CREDENTIAL_KEY_ID_INVALID", "credential key identifier is invalid"
        )
    return key_id


def _validate_keys(values: Mapping[str, bytes], domain: str) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for raw_key_id, raw_key in values.items():
        key_id = _validate_key_id(raw_key_id)
        key = bytes(raw_key)
        if len(key) != 32:
            raise CredentialVaultError(
                "CREDENTIAL_KEY_MATERIAL_INVALID",
                f"credential {domain} key must decode to exactly 32 bytes",
            )
        if key in result.values():
            raise CredentialVaultError(
                "CREDENTIAL_KEY_MATERIAL_DUPLICATE",
                f"credential {domain} key material must be unique",
            )
        result[key_id] = key
    return result


def _parse_key_map(raw_value: str | None, domain: str) -> dict[str, bytes]:
    try:
        parsed = json.loads(str(raw_value or ""))
    except json.JSONDecodeError as exc:
        raise CredentialVaultError(
            "CREDENTIAL_KEYRING_CONFIG_INVALID",
            f"credential {domain} keyring must be a JSON object",
        ) from exc
    if not isinstance(parsed, dict) or not parsed:
        raise CredentialVaultError(
            "CREDENTIAL_KEYRING_CONFIG_INVALID",
            f"credential {domain} keyring must be a non-empty JSON object",
        )
    result: dict[str, bytes] = {}
    for key_id, encoded in parsed.items():
        try:
            result[str(key_id)] = base64.b64decode(str(encoded), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise CredentialVaultError(
                "CREDENTIAL_KEY_MATERIAL_INVALID",
                f"credential {domain} key material must be valid base64",
            ) from exc
    return result
