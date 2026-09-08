"""Run SSLyze against the CSMS and print a summary of discovered crypto assets.

Usage:
    python setup/scan_tls.py [--host 127.0.0.1] [--port 9000]

The CSMS must already be running with TLS enabled:
    python -m CSMS.server --tls --port 9000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sslyze import (
    ClientAuthenticationCredentials,
    Scanner,
    ServerNetworkConfiguration,
    ServerNetworkLocation,
    ServerScanRequest,
    ScanCommand,
)
from sslyze.errors import ConnectionToServerFailed, ServerTlsConfigurationNotSupported

CERTS_DIR = Path(__file__).parent.parent / "certs"


def _run_scan(host: str, port: int, certfile: Path, keyfile: Path):
    location = ServerNetworkLocation(hostname=host, port=port)
    network_config = ServerNetworkConfiguration(
        tls_server_name_indication=host,
        tls_client_auth_credentials=ClientAuthenticationCredentials(
            certificate_chain_path=certfile,
            key_path=keyfile,
        ),
    )
    request = ServerScanRequest(
        server_location=location,
        network_configuration=network_config,
        scan_commands={
            ScanCommand.CERTIFICATE_INFO,
            ScanCommand.TLS_1_2_CIPHER_SUITES,
            ScanCommand.TLS_1_3_CIPHER_SUITES,
            ScanCommand.ELLIPTIC_CURVES,
        },
    )
    scanner = Scanner()
    scanner.queue_scans([request])
    return next(scanner.get_results())


def collect(host: str, port: int, certfile: Path, keyfile: Path) -> dict:
    """Run the scan and return structured discovery data."""
    result = _run_scan(host, port, certfile, keyfile)

    if result.connectivity_error_trace:
        raise ConnectionError(
            f"Could not connect to {host}:{port}: {result.connectivity_error_trace}"
        )

    data: dict = {"host": host, "port": port, "certificates": [], "tls_versions": [], "curves": []}
    scan = result.scan_result

    cert_attempt = scan.certificate_info
    if cert_attempt and cert_attempt.result:
        for deploy in cert_attempt.result.certificate_deployments:
            cert = deploy.received_certificate_chain[0]
            pub = cert.public_key()
            entry = {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "not_before": cert.not_valid_before_utc.isoformat(),
                "not_after": cert.not_valid_after_utc.isoformat(),
                "key_type": type(pub).__name__,
            }
            if hasattr(pub, "key_size"):
                entry["key_size"] = pub.key_size
            if hasattr(pub, "curve"):
                entry["curve"] = pub.curve.name
            data["certificates"].append(entry)

    for version, attempt in [("1.3", scan.tls_1_3_cipher_suites), ("1.2", scan.tls_1_2_cipher_suites)]:
        if attempt and attempt.result and attempt.result.accepted_cipher_suites:
            data["tls_versions"].append({
                "version": version,
                "cipher_suites": [s.cipher_suite.name for s in attempt.result.accepted_cipher_suites],
            })

    curves_attempt = scan.elliptic_curves
    if curves_attempt and curves_attempt.result and curves_attempt.result.supported_curves:
        data["curves"] = [c.name for c in curves_attempt.result.supported_curves]

    return data


def scan(host: str, port: int, certfile: Path, keyfile: Path) -> None:
    """Run the scan and print a human-readable summary."""
    try:
        data = collect(host, port, certfile, keyfile)
    except ConnectionError as e:
        print(e)
        return

    print(f"\n=== TLS Discovery: {host}:{port} ===\n")

    for cert in data["certificates"]:
        print("[Certificate]")
        print(f"  Subject:    {cert['subject']}")
        print(f"  Issuer:     {cert['issuer']}")
        print(f"  Not before: {cert['not_before']}")
        print(f"  Not after:  {cert['not_after']}")
        print(f"  Key type:   {cert['key_type']}")
        if "key_size" in cert:
            print(f"  Key size:   {cert['key_size']} bits")
        if "curve" in cert:
            print(f"  Curve:      {cert['curve']}")

    for tls in data["tls_versions"]:
        print(f"\n[TLS {tls['version']} Cipher Suites]")
        for suite in tls["cipher_suites"]:
            print(f"  {suite}")

    if data["curves"]:
        print("\n[Supported Elliptic Curves]")
        for curve in data["curves"]:
            print(f"  {curve}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--certfile", type=Path, default=CERTS_DIR / "charger1.crt")
    parser.add_argument("--keyfile", type=Path, default=CERTS_DIR / "charger1.key")
    args = parser.parse_args()
    scan(args.host, args.port, args.certfile, args.keyfile)


if __name__ == "__main__":
    main()
