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


def scan(host: str, port: int, certfile: Path, keyfile: Path) -> None:
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

    for result in scanner.get_results():
        if result.connectivity_error_trace:
            print(f"Could not connect to {host}:{port}")
            print(f"Error: {result.connectivity_error_trace}")
            return

        print(f"\n=== TLS Discovery: {host}:{port} ===\n")
        scan = result.scan_result

        cert_attempt = scan.certificate_info
        if cert_attempt and cert_attempt.result:
            for deploy in cert_attempt.result.certificate_deployments:
                cert = deploy.received_certificate_chain[0]
                print("[Certificate]")
                print(f"  Subject:    {cert.subject.rfc4514_string()}")
                print(f"  Issuer:     {cert.issuer.rfc4514_string()}")
                print(f"  Not before: {cert.not_valid_before_utc}")
                print(f"  Not after:  {cert.not_valid_after_utc}")
                pub = cert.public_key()
                print(f"  Key type:   {type(pub).__name__}")
                if hasattr(pub, 'key_size'):
                    print(f"  Key size:   {pub.key_size} bits")
                if hasattr(pub, 'curve'):
                    print(f"  Curve:      {pub.curve.name}")

        tls13 = scan.tls_1_3_cipher_suites
        if tls13 and tls13.result and tls13.result.accepted_cipher_suites:
            print("\n[TLS 1.3 Cipher Suites]")
            for suite in tls13.result.accepted_cipher_suites:
                print(f"  {suite.cipher_suite.name}")

        tls12 = scan.tls_1_2_cipher_suites
        if tls12 and tls12.result and tls12.result.accepted_cipher_suites:
            print("\n[TLS 1.2 Cipher Suites]")
            for suite in tls12.result.accepted_cipher_suites:
                print(f"  {suite.cipher_suite.name}")

        curves = scan.elliptic_curves
        if curves and curves.result and curves.result.supported_curves:
            print("\n[Supported Elliptic Curves]")
            for curve in curves.result.supported_curves:
                print(f"  {curve.name}")

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
