"""Generate self-signed CA and mTLS certificates for the EV charging testbed.

Outputs to certs/ directory:
  ca.crt                  - CA certificate (shared trust anchor)
  csms.crt / csms.key     - CSMS server certificate (ECDSA P-256)
  charger1.crt / .key     - Charger 1 client certificate (RSA-2048)
  charger2.crt / .key     - Charger 2 client certificate (ECDSA P-256)
"""

from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

CERTS_DIR = Path(__file__).parent.parent / "certs"
NOW = datetime.datetime.now(datetime.timezone.utc)
ONE_YEAR = NOW + datetime.timedelta(days=365)


def _save(path: Path, pem: bytes) -> None:
    path.write_bytes(pem)
    print(f"  wrote {path.relative_to(path.parent.parent)}")


def generate_ca() -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Project25 Test CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Project25"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(ONE_YEAR)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def generate_ecdsa_cert(
    common_name: str,
    ca_cert: x509.Certificate,
    ca_key: ec.EllipticCurvePrivateKey,
    is_server: bool = False,
    san_ips: list[str] | None = None,
) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Project25"),
    ])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(ONE_YEAR)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    usage = x509.KeyUsage(
        digital_signature=True, key_encipherment=False, content_commitment=False,
        data_encipherment=False, key_agreement=False, key_cert_sign=False,
        crl_sign=False, encipher_only=False, decipher_only=False,
    )
    builder = builder.add_extension(usage, critical=True)
    if is_server:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        sans: list[x509.GeneralName] = [x509.DNSName("localhost")]
        for ip in (san_ips or []):
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        builder = builder.add_extension(x509.SubjectAlternativeName(sans), critical=False)
    else:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
    return builder.sign(ca_key, hashes.SHA256()), key


def generate_rsa_cert(
    common_name: str,
    ca_cert: x509.Certificate,
    ca_key: ec.EllipticCurvePrivateKey,
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Project25"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(ONE_YEAR)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=True, content_commitment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return cert, key


def save_cert_and_key(stem: str, cert: x509.Certificate, key: object) -> None:
    _save(
        CERTS_DIR / f"{stem}.crt",
        cert.public_bytes(serialization.Encoding.PEM),
    )
    _save(
        CERTS_DIR / f"{stem}.key",
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ),
    )


def main() -> None:
    CERTS_DIR.mkdir(exist_ok=True)
    print("Generating certificates...")

    ca_cert, ca_key = generate_ca()
    _save(CERTS_DIR / "ca.crt", ca_cert.public_bytes(serialization.Encoding.PEM))

    csms_cert, csms_key = generate_ecdsa_cert(
        "csms.project25.local", ca_cert, ca_key,
        is_server=True,
        san_ips=["10.42.0.69", "127.0.0.1"],
    )
    save_cert_and_key("csms", csms_cert, csms_key)

    charger1_cert, charger1_key = generate_rsa_cert("CHARGER_01", ca_cert, ca_key)
    save_cert_and_key("charger1", charger1_cert, charger1_key)

    charger2_cert, charger2_key = generate_ecdsa_cert("CHARGER_02", ca_cert, ca_key)
    save_cert_and_key("charger2", charger2_cert, charger2_key)

    print("Done.")


if __name__ == "__main__":
    main()
