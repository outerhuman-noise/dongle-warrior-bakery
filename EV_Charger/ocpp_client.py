"""OCPP 2.0.1 client used by each simulated charging station."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import logging

import websockets

from ocpp.v201 import ChargePoint as OcppChargePoint
from ocpp.v201 import call, datatypes
from ocpp.v201.enums import (
    BootReasonEnumType,
    ConnectorStatusEnumType,
    RegistrationStatusEnumType,
)


LOGGER = logging.getLogger("project25.charger")
OCPP_SUBPROTOCOL = "ocpp2.0.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ChargerSettings:
    charge_point_id: str
    csms_url: str
    vendor_name: str = "Project 25"
    model: str = "RPi5 Simulator"
    reconnect_delay: float = 5.0

    @property
    def websocket_url(self) -> str:
        return f"{self.csms_url.rstrip('/')}/{self.charge_point_id}"


class SimulatedChargingStation(OcppChargePoint):
    async def send_boot_notification(
        self,
        vendor_name: str,
        model: str,
    ) -> int:
        response = await self.call(
            call.BootNotification(
                charging_station=datatypes.ChargingStationType(
                    vendor_name=vendor_name,
                    model=model,
                ),
                reason=BootReasonEnumType.power_up,
            )
        )

        if response.status != RegistrationStatusEnumType.accepted:
            raise RuntimeError(
                f"Central System rejected {self.id}: {response.status}"
            )

        LOGGER.info(
            "%s accepted by Central System; heartbeat interval=%ss",
            self.id,
            response.interval,
        )
        return response.interval

    async def send_heartbeat(self) -> None:
        await self.call(call.Heartbeat())
        LOGGER.info("Heartbeat acknowledged for %s", self.id)

    async def send_status(
        self,
        status: ConnectorStatusEnumType,
        *,
        evse_id: int = 1,
        connector_id: int = 1,
    ) -> None:
        await self.call(
            call.StatusNotification(
                timestamp=utc_now(),
                connector_status=status,
                evse_id=evse_id,
                connector_id=connector_id,
            )
        )


async def run_session(
    settings: ChargerSettings,
    *,
    heartbeat_limit: int | None = None,
) -> None:
    """Run one charger connection; heartbeat_limit is used by tests."""

    LOGGER.info(
        "%s connecting to %s",
        settings.charge_point_id,
        settings.websocket_url,
    )
    async with websockets.connect(
        settings.websocket_url,
        subprotocols=[OCPP_SUBPROTOCOL],
        ping_interval=20,
        ping_timeout=20,
        proxy=None,
    ) as websocket:
        station = SimulatedChargingStation(
            settings.charge_point_id,
            websocket,
        )
        listener = asyncio.create_task(station.start())

        try:
            heartbeat_interval = await station.send_boot_notification(
                settings.vendor_name,
                settings.model,
            )
            await station.send_status(ConnectorStatusEnumType.available)

            heartbeat_count = 0
            while heartbeat_limit is None or heartbeat_count < heartbeat_limit:
                await asyncio.sleep(heartbeat_interval)
                await station.send_heartbeat()
                heartbeat_count += 1
        finally:
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener


async def run_forever(settings: ChargerSettings) -> None:
    while True:
        try:
            await run_session(settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "%s lost its Central System connection; retrying in %.1fs",
                settings.charge_point_id,
                settings.reconnect_delay,
            )
            await asyncio.sleep(settings.reconnect_delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, dest="charge_point_id")
    parser.add_argument("--csms", default="ws://10.42.0.69:9000")
    parser.add_argument("--reconnect-delay", type=float, default=5.0)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = ChargerSettings(
        charge_point_id=args.charge_point_id,
        csms_url=args.csms,
        reconnect_delay=args.reconnect_delay,
    )
    asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
