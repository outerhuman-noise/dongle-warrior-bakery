#!/usr/bin/env python3
"""Run TLS discovery from RP7: start the CSMS on RP5, scan it from RP6.

Usage (from RP7):
    python Orchestrator/run_discovery.py --ask-password
    python Orchestrator/run_discovery.py --identity ~/.ssh/id_rsa
"""

from __future__ import annotations

import argparse
import getpass
import shlex
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import paramiko
from setup.generate_cbom import build_cbom
from setup.scan_tls import collect, CERTS_DIR

REPO_DIR = "/home/admin/dongle-warrior-bakery"
CSMS_HOST = "10.42.0.69"
DISCOVERY_HOST = "10.42.0.83"
CSMS_PORT = 9000


def ssh_connect(
    host: str,
    username: str,
    password: str | None,
    identity_file: str | None,
) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=host,
        username=username,
        password=password,
        key_filename=identity_file,
        timeout=10,
        look_for_keys=True,
        allow_agent=True,
    )
    return client


def start_background(
    client: paramiko.SSHClient,
    command: str,
    name: str,
) -> paramiko.Channel:
    channel = client.get_transport().open_session()
    channel.get_pty()
    channel.exec_command(f"cd {shlex.quote(REPO_DIR)} && {command}")
    print(f"[{name}] started")
    return channel


def run_and_stream(
    client: paramiko.SSHClient,
    command: str,
    name: str,
) -> int:
    channel = client.get_transport().open_session()
    channel.exec_command(f"cd {shlex.quote(REPO_DIR)} && {command}")

    while not channel.exit_status_ready():
        if channel.recv_ready():
            data = channel.recv(4096).decode(errors="replace")
            for line in data.splitlines():
                print(f"[{name}] {line}")
        if channel.recv_stderr_ready():
            data = channel.recv_stderr(4096).decode(errors="replace")
            for line in data.splitlines():
                print(f"[{name}][stderr] {line}", file=sys.stderr)
        time.sleep(0.05)

    while channel.recv_ready():
        data = channel.recv(4096).decode(errors="replace")
        for line in data.splitlines():
            print(f"[{name}] {line}")

    return channel.recv_exit_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--identity", help="SSH private-key path")
    parser.add_argument("--ask-password", action="store_true")
    parser.add_argument("--rp5-host", default=CSMS_HOST, help="CSMS IP")
    parser.add_argument("--rp6-host", default=DISCOVERY_HOST, help="Discovery node IP")
    parser.add_argument("--csms-port", type=int, default=CSMS_PORT)
    parser.add_argument("--certfile", type=Path, default=CERTS_DIR / "charger1.crt")
    parser.add_argument("--keyfile", type=Path, default=CERTS_DIR / "charger1.key")
    parser.add_argument("--out", type=Path, default=Path("cbom.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = (
        getpass.getpass(f"SSH password for {args.user}: ")
        if args.ask_password
        else None
    )

    rp5 = ssh_connect(args.rp5_host, args.user, password, args.identity)
    rp6 = ssh_connect(args.rp6_host, args.user, password, args.identity)

    csms_channel = start_background(
        rp5,
        ".venv/bin/python -m CSMS.server --tls --port " + str(args.csms_port),
        "rp5-csms",
    )

    print(f"[rp5-csms] waiting for CSMS to start...")
    time.sleep(3)

    if csms_channel.exit_status_ready():
        print("[rp5-csms] CSMS failed to start — aborting", file=sys.stderr)
        rp5.close()
        rp6.close()
        sys.exit(1)

    def stop_all(*_: object) -> None:
        print("\nStopping...")
        csms_channel.send("\x03")
        time.sleep(0.2)
        csms_channel.close()
        rp5.close()
        rp6.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    print(f"\n[rp6] running TLS discovery against {args.rp5_host}:{args.csms_port}\n")
    scan_command = (
        f".venv/bin/python setup/scan_tls.py"
        f" --host {shlex.quote(args.rp5_host)}"
        f" --port {args.csms_port}"
    )
    exit_code = run_and_stream(rp6, scan_command, "rp6-scan")
    print(f"\n[rp6] scan completed with exit code {exit_code}")

    if exit_code == 0:
        print(f"\nGenerating CBOM from {args.rp5_host}:{args.csms_port}...")
        try:
            data = collect(args.rp5_host, args.csms_port, args.certfile, args.keyfile)
            cbom = build_cbom(data, "CSMS")
            import json
            args.out.write_text(json.dumps(cbom, indent=2))
            print(f"CBOM written to {args.out} ({len(cbom['components'])} assets)")
        except Exception as e:
            print(f"CBOM generation failed: {e}", file=sys.stderr)

    stop_all()


if __name__ == "__main__":
    main()
