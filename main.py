"""Start the OCPP service assigned to this Raspberry Pi hostname."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import socket
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"


def load_config(
    hostname: str | None = None,
    config_dir: Path = DEFAULT_CONFIG_DIR,
) -> dict[str, Any]:
    selected_hostname = hostname or socket.gethostname()
    config_path = config_dir / f"{selected_hostname}.json"

    if not config_path.is_file():
        raise FileNotFoundError(
            f"No configuration for {selected_hostname}: {config_path}"
        )

    with config_path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


async def run_config(config: dict[str, Any]) -> None:
    role = config.get("role")

    if role == "csms":
        from CSMS.server import serve_forever

        await serve_forever(
            host=config.get("host", "0.0.0.0"),
            port=config.get("port", 9000),
            heartbeat_interval=config.get("heartbeat_interval", 10),
        )
        return

    if role == "charger":
        from EV_Charger.ocpp_client import ChargerSettings, run_forever

        await run_forever(
            ChargerSettings(
                charge_point_id=config["charge_point_id"],
                csms_url=config["csms_url"],
                vendor_name=config.get("vendor_name", "Project 25"),
                model=config.get("model", "RPi5 Simulator"),
                reconnect_delay=config.get("reconnect_delay", 5.0),
            )
        )
        return

    if role == "ev":
        raise SystemExit(
            "The EV simulators still use EV/test_client.py. "
            "They will be integrated after the OCPP milestone."
        )

    if role in {"orchestrator", "reserved"}:
        print(f"No long-running OCPP service is assigned to role: {role}")
        return

    raise ValueError(f"Unsupported role in configuration: {role!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hostname",
        help="Override socket.gethostname() for local testing",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.hostname, args.config_dir)
    logging.basicConfig(
        level=getattr(
            logging,
            str(config.get("log_level", "INFO")).upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_config(config))


if __name__ == "__main__":
    main()

