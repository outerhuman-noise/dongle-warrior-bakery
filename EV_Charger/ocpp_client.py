"""OCPP 2.0.1 client used by each simulated charging station."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import re
import ssl

import websockets

CERTS_DIR = Path(__file__).parent.parent / "certs"

from EV_Charger.ev_charger import start_ev_server
from ocpp.v201 import ChargePoint as OcppChargePoint
from ocpp.v201 import call, datatypes
from ocpp.v201.enums import (
    BootReasonEnumType,
    ConnectorStatusEnumType,
    RegistrationStatusEnumType,
    TransactionEventEnumType,
    TriggerReasonEnumType,
    ChargingStateEnumType,
)


LOGGER = logging.getLogger("project25.charger")
OCPP_SUBPROTOCOL = "ocpp2.0.1"


def build_ssl_context(
    certfile: Path,
    keyfile: Path,
    cafile: Path,
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_cert_chain(certfile, keyfile)
    ctx.load_verify_locations(cafile)
    return ctx


def default_certificate_stem(charge_point_id: str) -> str:
    """Map testbed charge-point IDs to generated certificate filenames."""

    match = re.fullmatch(r"CHARGER_0*(\d+)", charge_point_id, re.IGNORECASE)
    if match:
        return f"charger{int(match.group(1))}"
    return charge_point_id.lower()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ChargerSettings:
    charge_point_id: str
    csms_url: str
    vendor_name: str = "Project 25"
    model: str = "RPi5 Simulator"
    reconnect_delay: float = 5.0
    session_interval: float = 60.0
    session_duration: float = 30.0
    ev_port: int | None = None
    ssl_context: ssl.SSLContext | None = None

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

    async def send_transaction_event(
            self,
            event_type: TransactionEventEnumType,
            trigger_reason: TriggerReasonEnumType,
            seq_no: int,
            transaction_id: str,
            charging_state: ChargingStateEnumType=None,
            id_token: dict=None,
            meter_value: list=None,
            evse_id: int=None,
            connector_id: int=None,
    ):
        transaction_info = {"transaction_id": transaction_id}
        if charging_state is not None:
            transaction_info["charging_state"] = charging_state

        response = await self.call(
            call.TransactionEvent(
                event_type=event_type.value,
                timestamp=utc_now(),
                trigger_reason=trigger_reason.value,
                seq_no=seq_no,
                transaction_info=transaction_info,
                id_token=id_token,
                meter_value=meter_value,
                evse={"id": evse_id, "connector_id": connector_id} if evse_id else None,
            )
        )
        LOGGER.info("Transaction Event %s acknowledged for %s", event_type, self.id)

    async def simulate_charging_session(
            self,
            transaction_id: str,
            session_duration: float,
    ) -> None:
        await self.send_status(ConnectorStatusEnumType.occupied)
        await self.send_transaction_event(
            TransactionEventEnumType.started,
            TriggerReasonEnumType.cable_plugged_in,
            seq_no=0,
            transaction_id=transaction_id,
        )
        await asyncio.sleep(session_duration)
        await self.send_transaction_event(
            TransactionEventEnumType.ended,
            TriggerReasonEnumType.ev_departed,
            seq_no=1,
            transaction_id=transaction_id,
        )
        await self.send_status(ConnectorStatusEnumType.available)


async def run_session(
    settings: ChargerSettings,
    *,
    heartbeat_limit: int | None = None,
) -> None:
    """Run one charger connection; heartbeat_limit enables one-shot tests."""

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
        ssl=settings.ssl_context,
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

            async def heartbeat_loop() -> None:
                count = 0
                while heartbeat_limit is None or count < heartbeat_limit:
                    await asyncio.sleep(heartbeat_interval)
                    await station.send_heartbeat()
                    count += 1

            async def session_loop() -> None:
                session_count = 0
                while True:
                    await asyncio.sleep(settings.session_interval)
                    session_count += 1
                    tx_id = f"{settings.charge_point_id}-TX-{session_count}"
                    await station.simulate_charging_session(tx_id, settings.session_duration)

            loops = [heartbeat_loop()]
            ev_server = None
            if heartbeat_limit is None:
                if settings.ev_port is not None:
                    ev_server = await start_ev_server(
                        station,
                        settings.session_duration,
                        port=settings.ev_port,
                    )
                else:
                    loops.append(session_loop())

            try:
                await asyncio.gather(*loops)
            finally:
                if ev_server is not None:
                    ev_server.close()
                    await ev_server.wait_closed()
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
    parser.add_argument("--tls", action="store_true", help="Enable mTLS")
    parser.add_argument("--certfile", type=Path, default=None)
    parser.add_argument("--keyfile", type=Path, default=None)
    parser.add_argument("--cafile", type=Path, default=CERTS_DIR / "ca.crt")
    parser.add_argument(
        "--heartbeat-limit",
        type=int,
        help="Exit after this many acknowledged heartbeats (smoke-test mode)",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ssl_context = None
    if args.tls:
        certificate_stem = default_certificate_stem(args.charge_point_id)
        certfile = args.certfile or CERTS_DIR / f"{certificate_stem}.crt"
        keyfile = args.keyfile or CERTS_DIR / f"{certificate_stem}.key"
        ssl_context = build_ssl_context(certfile, keyfile, args.cafile)
    settings = ChargerSettings(
        charge_point_id=args.charge_point_id,
        csms_url=args.csms,
        reconnect_delay=args.reconnect_delay,
        ssl_context=ssl_context,
    )
    if args.heartbeat_limit is not None:
        if args.heartbeat_limit < 1:
            raise SystemExit("--heartbeat-limit must be at least 1")
        asyncio.run(run_session(settings, heartbeat_limit=args.heartbeat_limit))
    else:
        asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
