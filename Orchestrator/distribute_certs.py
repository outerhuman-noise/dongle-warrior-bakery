#!/usr/bin/env python3
"""Generate certificates on RP7 and distribute them to the fleet.

Run this once from RP7 to set up mTLS across all Pis:
    python3 Orchestrator/distribute_certs.py --ask-password

What it does:
  1. Runs setup/generate_certs.py locally (on RP7) to create all certs
  2. Copies the right certs to each Pi over SCP:
       RP5 (CSMS)        <- ca.crt, csms.crt, csms.key
       RP1 (Charger 1)   <- ca.crt, charger1.crt, charger1.key
       RP3 (Charger 2)   <- ca.crt, charger2.crt, charger2.key
       RP6 (Discovery)   <- ca.crt, charger1.crt, charger1.key
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

import paramiko

REPO_DIR = "/home/admin/dongle-warrior-bakery"
CERTS_DIR = Path(__file__).parent.parent / "certs"

FLEET: list[dict] = [
    {
        "name": "rp5-csms",
        "host": "10.42.0.69",
        "certs": ["ca.crt", "csms.crt", "csms.key"],
    },
    {
        "name": "rp1-charger1",
        "host": "10.42.0.222",
        "certs": ["ca.crt", "charger1.crt", "charger1.key"],
    },
    {
        "name": "rp3-charger2",
        "host": "10.42.0.215",
        "certs": ["ca.crt", "charger2.crt", "charger2.key"],
    },
    {
        "name": "rp6-discovery",
        "host": "10.42.0.83",
        "certs": ["ca.crt", "charger1.crt", "charger1.key"],
    },
]


def generate_certs() -> None:
    print("Generating certificates...")
    script = Path(__file__).parent.parent / "setup" / "generate_certs.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(Path(__file__).parent.parent),
    )
    if result.returncode != 0:
        print("Certificate generation failed", file=sys.stderr)
        sys.exit(1)
    print()


def distribute_certs(
    username: str,
    password: str | None,
    identity_file: str | None,
) -> None:
    for pi in FLEET:
        print(f"[{pi['name']}] connecting to {pi['host']}...")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=pi["host"],
                username=username,
                password=password,
                key_filename=identity_file,
                timeout=10,
                look_for_keys=True,
                allow_agent=True,
            )
        except Exception as e:
            print(f"[{pi['name']}] connection failed: {e}", file=sys.stderr)
            continue

        remote_certs_dir = f"{REPO_DIR}/certs"
        _, stdout, _ = client.exec_command(f"mkdir -p {remote_certs_dir}")
        stdout.channel.recv_exit_status()

        sftp = client.open_sftp()
        for cert_name in pi["certs"]:
            local_path = CERTS_DIR / cert_name
            remote_path = f"{remote_certs_dir}/{cert_name}"
            sftp.put(str(local_path), remote_path)
            print(f"[{pi['name']}] copied {cert_name}")
        sftp.close()
        client.close()
        print(f"[{pi['name']}] done\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--identity", help="SSH private-key path")
    parser.add_argument("--ask-password", action="store_true")
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip cert generation and only distribute existing certs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = (
        getpass.getpass(f"SSH password for {args.user}: ")
        if args.ask_password
        else None
    )

    if not args.skip_generate:
        generate_certs()

    distribute_certs(args.user, password, args.identity)
    print("Certificate distribution complete.")


if __name__ == "__main__":
    main()
