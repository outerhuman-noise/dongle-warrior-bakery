"""Generate a CycloneDX 1.6 CBOM from a live TLS scan of the CSMS.

Usage:
    python setup/generate_cbom.py [--host 127.0.0.1] [--port 9000] [--out cbom.json]

The CSMS must already be running with TLS enabled.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from setup.scan_tls import collect, CERTS_DIR


def _bom_ref(name: str) -> str:
    return name.lower().replace(" ", "-").replace("_", "-")


def build_cbom(data: dict, component_name: str) -> dict:
    components = []

    for cert in data["certificates"]:
        ref = _bom_ref(f"cert-{cert['subject']}")
        entry: dict = {
            "bom-ref": ref,
            "type": "cryptographic-asset",
            "name": cert["subject"],
            "cryptoProperties": {
                "assetType": "certificate",
                "certificateProperties": {
                    "subjectName": cert["subject"],
                    "issuerName": cert["issuer"],
                    "notValidBefore": cert["not_before"],
                    "notValidAfter": cert["not_after"],
                    "certificateFormat": "X.509",
                },
            },
        }
        if "curve" in cert:
            entry["cryptoProperties"]["certificateProperties"]["signatureAlgorithm"] = (
                f"ECDSA-{cert['curve']}"
            )
        elif "key_size" in cert:
            entry["cryptoProperties"]["certificateProperties"]["signatureAlgorithm"] = (
                f"RSA-{cert['key_size']}"
            )
        components.append(entry)

        if "curve" in cert:
            algo_ref = _bom_ref(f"algo-ecdsa-{cert['curve']}")
            components.append({
                "bom-ref": algo_ref,
                "type": "cryptographic-asset",
                "name": "ECDSA",
                "cryptoProperties": {
                    "assetType": "algorithm",
                    "algorithmProperties": {
                        "primitive": "signature",
                        "curve": cert["curve"],
                        "classicalSecurityLevel": 128 if cert["key_size"] == 256 else 192,
                    },
                },
            })
        elif "key_size" in cert:
            algo_ref = _bom_ref(f"algo-rsa-{cert['key_size']}")
            components.append({
                "bom-ref": algo_ref,
                "type": "cryptographic-asset",
                "name": "RSA",
                "cryptoProperties": {
                    "assetType": "algorithm",
                    "algorithmProperties": {
                        "primitive": "signature",
                        "parameterSetIdentifier": str(cert["key_size"]),
                        "classicalSecurityLevel": 112 if cert["key_size"] == 2048 else 128,
                    },
                },
            })

    for tls in data["tls_versions"]:
        ref = _bom_ref(f"proto-tls-{tls['version']}")
        components.append({
            "bom-ref": ref,
            "type": "cryptographic-asset",
            "name": f"TLS {tls['version']}",
            "cryptoProperties": {
                "assetType": "protocol",
                "protocolProperties": {
                    "type": "tls",
                    "version": tls["version"],
                    "cipherSuites": [
                        {"name": name} for name in tls["cipher_suites"]
                    ],
                },
            },
        })

    for curve in data["curves"]:
        ref = _bom_ref(f"algo-{curve}")
        components.append({
            "bom-ref": ref,
            "type": "cryptographic-asset",
            "name": curve,
            "cryptoProperties": {
                "assetType": "algorithm",
                "algorithmProperties": {
                    "primitive": "key-agree",
                    "curve": curve,
                },
            },
        })

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "device",
                "name": component_name,
                "description": f"TLS discovery of {data['host']}:{data['port']}",
            },
        },
        "components": components,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--certfile", type=Path, default=CERTS_DIR / "charger1.crt")
    parser.add_argument("--keyfile", type=Path, default=CERTS_DIR / "charger1.key")
    parser.add_argument("--component", default="CSMS", help="Name of the scanned component")
    parser.add_argument("--out", type=Path, default=Path("cbom.json"))
    args = parser.parse_args()

    print(f"Scanning {args.host}:{args.port}...")
    data = collect(args.host, args.port, args.certfile, args.keyfile)

    cbom = build_cbom(data, args.component)

    args.out.write_text(json.dumps(cbom, indent=2))
    print(f"CBOM written to {args.out}")
    print(f"  {len(cbom['components'])} cryptographic assets discovered")


if __name__ == "__main__":
    main()
