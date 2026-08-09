#!/usr/bin/env python3
"""Create the private CA and service certificates for single-node AIRank.

The command is fail-closed: it never overwrites an existing PKI directory and
prints only public certificate metadata.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
from typing import Sequence

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


CERTIFICATE_SPECS = (
    ("mysql-server", ("airank-db", "mysql")),
    ("minio", ("airank-objects", "minio")),
    ("yudao-proxy", ("airank-yudao", "yudao-proxy")),
)
EXPECTED_FILES = {
    "ca.pem",
    "ca-bundle.pem",
    "ca-key.pem",
    "mysql-server.pem",
    "mysql-server-key.pem",
    "minio-public.crt",
    "minio-private.key",
    "yudao-proxy.crt",
    "yudao-proxy.key",
    "manifest.json",
}


def _private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def _write(path: Path, payload: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _certificate_bytes(certificate: x509.Certificate) -> bytes:
    return certificate.public_bytes(serialization.Encoding.PEM)


def _key_bytes(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_record(name: str, certificate: x509.Certificate) -> dict[str, str]:
    der = certificate.public_bytes(serialization.Encoding.DER)
    return {
        "name": name,
        "not_before": certificate.not_valid_before_utc.isoformat(),
        "not_after": certificate.not_valid_after_utc.isoformat(),
        "sha256": hashlib.sha256(der).hexdigest(),
    }


def _system_ca_bundle() -> bytes:
    cafile = ssl.get_default_verify_paths().cafile
    if not cafile:
        raise FileNotFoundError("system CA bundle path is unavailable")
    payload = Path(cafile).read_bytes()
    if b"-----BEGIN CERTIFICATE-----" not in payload:
        raise ValueError("system CA bundle does not contain PEM certificates")
    return payload.rstrip() + b"\n"


def provision_pki(output_dir: Path, *, now: datetime | None = None) -> dict[str, object]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = sorted(path.name for path in output_dir.iterdir() if path.name in EXPECTED_FILES)
    if existing:
        raise FileExistsError(
            "refusing to overwrite existing PKI files: " + ", ".join(existing)
        )

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    not_before = current - timedelta(minutes=5)
    ca_key = _private_key()
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "AIRank single-node internal CA")]
    )
    ca_certificate = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(current + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    created: list[Path] = []
    records = [_public_record("ca", ca_certificate)]
    try:
        ca_payload = _certificate_bytes(ca_certificate)
        for name, payload, mode in (
            ("ca-key.pem", _key_bytes(ca_key), 0o600),
            ("ca.pem", ca_payload, 0o644),
            ("ca-bundle.pem", _system_ca_bundle() + ca_payload, 0o644),
        ):
            path = output_dir / name
            _write(path, payload, mode)
            created.append(path)

        for service_name, dns_names in CERTIFICATE_SPECS:
            key = _private_key()
            subject = x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, dns_names[0])]
            )
            certificate = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(ca_name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(not_before)
                .not_valid_after(current + timedelta(days=825))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(name) for name in dns_names]),
                    critical=False,
                )
                .add_extension(
                    x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                    critical=False,
                )
                .sign(ca_key, hashes.SHA256())
            )
            if service_name == "minio":
                cert_filename = "minio-public.crt"
                key_filename = "minio-private.key"
            elif service_name == "yudao-proxy":
                cert_filename = "yudao-proxy.crt"
                key_filename = "yudao-proxy.key"
            else:
                cert_filename = f"{service_name}.pem"
                key_filename = f"{service_name}-key.pem"
            for filename, payload, mode in (
                (cert_filename, _certificate_bytes(certificate), 0o644),
                (key_filename, _key_bytes(key), 0o600),
            ):
                path = output_dir / filename
                _write(path, payload, mode)
                created.append(path)
            records.append(_public_record(service_name, certificate))

        manifest = {
            "status": "pass",
            "generated_at": current.isoformat(),
            "certificates": records,
            "trust_bundle_sha256": hashlib.sha256(
                (output_dir / "ca-bundle.pem").read_bytes()
            ).hexdigest(),
        }
        manifest_path = output_dir / "manifest.json"
        _write(
            manifest_path,
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
            0o644,
        )
        created.append(manifest_path)
        return manifest
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(list(argv) if argv is not None else os.sys.argv[1:])
    try:
        record = provision_pki(args.output_dir)
    except (FileExistsError, OSError) as exc:
        print(
            json.dumps(
                {"status": "blocked", "error_type": type(exc).__name__},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
