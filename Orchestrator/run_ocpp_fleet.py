#!/usr/bin/env python3
"""Start the CSMS and both OCPP charger clients from dongle-rp7."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import getpass
import json
from pathlib import Path
import shlex
import signal
import socket
import sys
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import paramiko


DEFAULT_INVENTORY = Path(__file__).with_name("ocpp_fleet.json")
SUCCESS_MARKERS = (
    "accepted by Central System",
    "Heartbeat acknowledged",
)


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


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    output: str
    timed_out: bool = False


def certificate_stem(charge_point_id: str) -> str:
    digits = "".join(character for character in charge_point_id if character.isdigit())
    if charge_point_id.upper().startswith("CHARGER_") and digits:
        return f"charger{int(digits)}"
    return charge_point_id.lower()


def normalize_csms_url(url: str, tls: bool) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise ValueError("CSMS URL must use ws:// or wss:// and include a hostname")
    if tls and parsed.scheme == "ws":
        parsed = parsed._replace(scheme="wss")
    if not tls and parsed.scheme == "wss":
        raise ValueError("Use --tls when the CSMS URL starts with wss://")
    return urlunsplit(parsed)


def csms_endpoint(url: str) -> tuple[str, int]:
    parsed = urlsplit(url)
    if not parsed.hostname:
        raise ValueError("CSMS URL does not contain a hostname")
    return parsed.hostname, parsed.port or (443 if parsed.scheme == "wss" else 80)


def build_smoke_command(
    *,
    repo_dir: str,
    charger_id: str,
    csms_url: str,
    tls: bool,
    cert_stem: str,
) -> str:
    client_args = [
        ".venv/bin/python",
        "-m",
        "EV_Charger.ocpp_client",
        "--id",
        charger_id,
        "--csms",
        csms_url,
        "--heartbeat-limit",
        "1",
    ]
    if tls:
        client_args.extend(
            [
                "--tls",
                "--certfile",
                f"certs/{cert_stem}.crt",
                "--keyfile",
                f"certs/{cert_stem}.key",
                "--cafile",
                "certs/ca.crt",
            ]
        )

    return (
        f"cd {shlex.quote(repo_dir)} && "
        "if [ ! -x .venv/bin/python ]; then "
        "echo 'Missing .venv; create it and install requirements first.' >&2; "
        "exit 2; fi; "
        f"exec {shlex.join(client_args)}"
    )


def probe_csms(url: str, timeout: float) -> None:
    host, port = csms_endpoint(url)
    with socket.create_connection((host, port), timeout=timeout):
        return


def drain_channel(channel: paramiko.Channel, chunks: list[str]) -> None:
    while channel.recv_ready():
        output = channel.recv(4096).decode(errors="replace")
        chunks.append(output)
        print(output, end="", flush=True)
    while channel.recv_stderr_ready():
        output = channel.recv_stderr(4096).decode(errors="replace")
        chunks.append(output)
        print(output, end="", file=sys.stderr, flush=True)


def run_remote_command(
    channel: paramiko.Channel,
    command: str,
    timeout: float,
) -> CommandResult:
    channel.get_pty()
    channel.exec_command(command)
    deadline = time.monotonic() + timeout
    chunks: list[str] = []

    while True:
        drain_channel(channel, chunks)
        if channel.exit_status_ready():
            drain_channel(channel, chunks)
            return CommandResult(channel.recv_exit_status(), "".join(chunks))
        if time.monotonic() >= deadline:
            channel.send("\x03")
            time.sleep(0.1)
            drain_channel(channel, chunks)
            channel.close()
            return CommandResult(124, "".join(chunks), timed_out=True)
        time.sleep(0.05)


def smoke_test_passed(result: CommandResult) -> bool:
    return (
        result.exit_code == 0
        and not result.timed_out
        and all(marker in result.output for marker in SUCCESS_MARKERS)
    )


def write_smoke_log(
    log_dir: Path,
    *,
    service: dict[str, Any],
    charger_id: str,
    csms_url: str,
    result: CommandResult,
) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = log_dir / f"ocpp-{charger_id.lower()}-{timestamp}.log"
    header = (
        f"service={service['name']}\n"
        f"charger_host={service['host']}\n"
        f"charger_id={charger_id}\n"
        f"csms_url={csms_url}\n"
        f"exit_code={result.exit_code}\n"
        f"timed_out={result.timed_out}\n\n"
    )
    path.write_text(header + result.output, encoding="utf-8")
    return path


def load_inventory(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as inventory_file:
        inventory = json.load(inventory_file)

    if not inventory.get("services"):
        raise ValueError("The OCPP fleet inventory contains no services")
    return inventory


def find_service(inventory: dict[str, Any], name: str) -> dict[str, Any]:
    for service in inventory["services"]:
        if service.get("name") == name:
            return service
    available = ", ".join(service.get("name", "<unnamed>") for service in inventory["services"])
    raise ValueError(f"Unknown service {name!r}; available services: {available}")


def run_smoke_test(
    args: argparse.Namespace,
    inventory: dict[str, Any],
    *,
    repo_dir: str,
    password: str | None,
) -> int:
    try:
        service = find_service(inventory, args.smoke_test)
        charger_id = service["charge_point_id"]
        csms_url = normalize_csms_url(
            args.csms_url or inventory.get("csms_url", "ws://10.42.0.69:9000"),
            args.tls,
        )
    except (KeyError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    print("OCPP charger-to-CSMS smoke test")
    print(f"  CSMS:    {csms_url}")
    print(f"  Charger: {charger_id} on {service['host']}")

    if not args.skip_port_check:
        try:
            probe_csms(csms_url, args.connect_timeout)
        except OSError as error:
            print(f"FAIL: CSMS TCP port is not reachable: {error}", file=sys.stderr)
            return 2
        print("  Preflight: CSMS TCP port is reachable")

    command = build_smoke_command(
        repo_dir=repo_dir,
        charger_id=charger_id,
        csms_url=csms_url,
        tls=args.tls,
        cert_stem=args.cert_stem or service.get(
            "certificate_stem", certificate_stem(charger_id)
        ),
    )
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())

    try:
        client.connect(
            hostname=service["host"],
            username=args.user,
            password=password,
            key_filename=args.identity,
            timeout=args.connect_timeout,
            look_for_keys=True,
            allow_agent=True,
        )
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport was not created")
        result = run_remote_command(
            transport.open_session(),
            command,
            args.timeout,
        )
    except paramiko.AuthenticationException:
        print("FAIL: SSH authentication failed. Use --ask-password or --identity.", file=sys.stderr)
        return 2
    except paramiko.SSHException as error:
        print(f"FAIL: SSH error: {error}", file=sys.stderr)
        print(
            f"Connect once with 'ssh {args.user}@{service['host']}' to trust its host key.",
            file=sys.stderr,
        )
        return 2
    except (OSError, RuntimeError) as error:
        print(f"FAIL: Could not run the remote charger: {error}", file=sys.stderr)
        return 2
    finally:
        client.close()

    log_path = write_smoke_log(
        args.log_dir,
        service=service,
        charger_id=charger_id,
        csms_url=csms_url,
        result=result,
    )
    print(f"\nLog saved to {log_path}")

    if smoke_test_passed(result):
        print("PASS: BootNotification accepted and Heartbeat acknowledged.")
        return 0
    if result.timed_out:
        print("FAIL: Timed out waiting for the charger smoke test to finish.", file=sys.stderr)
    else:
        missing = [marker for marker in SUCCESS_MARKERS if marker not in result.output]
        print(
            f"FAIL: Remote exit code {result.exit_code}; missing output: {missing}",
            file=sys.stderr,
        )
    return 1


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
    parser.add_argument(
        "--smoke-test",
        nargs="?",
        const="charger-01",
        metavar="SERVICE",
        help="Test one inventory charger and exit (default: charger-01)",
    )
    parser.add_argument("--csms-url", help="Override the inventory CSMS URL")
    parser.add_argument("--tls", action="store_true", help="Use mTLS and wss://")
    parser.add_argument("--cert-stem", help="Override the remote certificate filename stem")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--log-dir", type=Path, default=Path("captures"))
    parser.add_argument(
        "--skip-port-check",
        action="store_true",
        help="Skip the RP7-to-CSMS TCP reachability check",
    )
    return parser.parse_args()


def main() -> int:
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

    if args.timeout <= 0 or args.connect_timeout <= 0:
        print("Timeouts must be greater than zero.", file=sys.stderr)
        return 2
    if args.smoke_test is not None:
        return run_smoke_test(
            args,
            inventory,
            repo_dir=repo_dir,
            password=password,
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
