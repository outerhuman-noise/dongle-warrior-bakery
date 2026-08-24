#!/usr/bin/env python3
"""Start the CSMS and both OCPP charger clients from dongle-rp7."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import getpass
import json
from pathlib import Path
import shlex
import signal
import sys
import time
from typing import Any

import paramiko


DEFAULT_INVENTORY = Path(__file__).with_name("ocpp_fleet.json")


@dataclass
class RemoteService:
    name: str
    client: paramiko.SSHClient
    channel: paramiko.Channel

    def stream_output(self) -> None:
        while self.channel.recv_ready():
            output = self.channel.recv(4096).decode(errors="replace")
            for line in output.splitlines():
                print(f"[{self.name}] {line}")

        while self.channel.recv_stderr_ready():
            output = self.channel.recv_stderr(4096).decode(errors="replace")
            for line in output.splitlines():
                print(f"[{self.name}][stderr] {line}", file=sys.stderr)

    def stop(self) -> None:
        if not self.channel.closed:
            self.channel.send("\x03")
            time.sleep(0.1)
            self.channel.close()
        self.client.close()


def load_inventory(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as inventory_file:
        inventory = json.load(inventory_file)

    if not inventory.get("services"):
        raise ValueError("The OCPP fleet inventory contains no services")
    return inventory


def start_remote_service(
    service: dict[str, Any],
    *,
    username: str,
    repo_dir: str,
    password: str | None,
    identity_file: str | None,
) -> RemoteService:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=service["host"],
        username=username,
        password=password,
        key_filename=identity_file,
        timeout=10,
        look_for_keys=True,
        allow_agent=True,
    )

    command = (
        f"cd {shlex.quote(repo_dir)} && "
        f"exec {service['command']}"
    )
    channel = client.get_transport().open_session()
    channel.get_pty()
    channel.exec_command(command)
    print(f"[{service['name']}] started on {service['host']}")

    return RemoteService(service["name"], client, channel)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--user", default="admin")
    parser.add_argument("--identity", help="SSH private-key path")
    parser.add_argument(
        "--ask-password",
        action="store_true",
        help="Prompt securely if SSH keys are not configured",
    )
    parser.add_argument(
        "--startup-delay",
        type=float,
        default=2.0,
        help="Delay between startup-order groups",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    inventory = load_inventory(args.inventory)
    repo_dir = inventory.get(
        "repo_dir", "/home/admin/dongle-warrior-bakery"
    )
    password = (
        getpass.getpass(f"SSH password for {args.user}: ")
        if args.ask_password
        else None
    )

    services = sorted(
        inventory["services"],
        key=lambda item: item.get("startup_order", 100),
    )
    running: list[RemoteService] = []
    current_order: int | None = None

    def stop_all(*_: object) -> None:
        print("\nStopping OCPP fleet...")
        for remote in reversed(running):
            remote.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    try:
        for service in services:
            order = service.get("startup_order", 100)
            if current_order is not None and order != current_order:
                time.sleep(args.startup_delay)
                for remote in running:
                    remote.stream_output()
                    if remote.channel.exit_status_ready():
                        raise RuntimeError(
                            f"{remote.name} stopped during startup"
                        )

            running.append(
                start_remote_service(
                    service,
                    username=args.user,
                    repo_dir=repo_dir,
                    password=password,
                    identity_file=args.identity,
                )
            )
            current_order = order

        print("OCPP fleet is running. Press Ctrl+C to stop it.")
        while True:
            active = 0
            for remote in running:
                remote.stream_output()
                if remote.channel.exit_status_ready():
                    exit_code = remote.channel.recv_exit_status()
                    print(f"[{remote.name}] exited with code {exit_code}")
                else:
                    active += 1

            if active == 0:
                break
            time.sleep(0.1)
    finally:
        for remote in reversed(running):
            remote.stop()


if __name__ == "__main__":
    main()

