"""Minimal OCPP 2.0.1 Central System for the Raspberry Pi testbed."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import unquote, urlsplit

import websockets
from websockets.exceptions import ConnectionClosed

from ocpp.routing import on
from ocpp.v201 import ChargePoint as OcppChargePoint
from ocpp.v201 import call_result
from ocpp.v201.enums import Action, RegistrationStatusEnumType


LOGGER = logging.getLogger("project25.csms")
OCPP_SUBPROTOCOL = "ocpp2.0.1"


def utc_now() -> str:
    """Return an OCPP-compatible UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def extract_charge_point_id(request_path: str) -> str | None:
    """Extract the final URL path segment used as the OCPP station ID."""

    path = urlsplit(request_path).path.rstrip("/")
    if not path:
        return None
    charge_point_id = unquote(path.rsplit("/", 1)[-1]).strip()
    return charge_point_id or None


@dataclass
class StationRecord:
    """In-memory state for one connected charging station."""

    charge_point_id: str
    connected: bool = False
    charging_station: dict[str, Any] = field(default_factory=dict)
    boot_reason: str | None = None
    boot_count: int = 0
    heartbeat_count: int = 0
    last_seen: str | None = None
    status_notifications: list[dict[str, Any]] = field(default_factory=list)
    transaction_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CentralSystemState:
    """State shared by all OCPP connections."""

    stations: dict[str, StationRecord] = field(default_factory=dict)

    def station(self, charge_point_id: str) -> StationRecord:
        return self.stations.setdefault(
            charge_point_id,
            StationRecord(charge_point_id=charge_point_id),
        )

    def set_connected(self, charge_point_id: str, connected: bool) -> None:
        record = self.station(charge_point_id)
        record.connected = connected
        record.last_seen = utc_now()


class CentralSystemChargePoint(OcppChargePoint):
    """Server-side representation of a connected charging station."""

    def __init__(
        self,
        charge_point_id: str,
        connection: Any,
        state: CentralSystemState,
        heartbeat_interval: int,
    ) -> None:
        super().__init__(charge_point_id, connection)
        self.state = state
        self.heartbeat_interval = heartbeat_interval

    @on(Action.boot_notification)
    def on_boot_notification(
        self,
        charging_station: dict[str, Any],
        reason: str,
        **_: Any,
    ) -> call_result.BootNotification:
        record = self.state.station(self.id)
        record.connected = True
        record.charging_station = charging_station
        record.boot_reason = reason
        record.boot_count += 1
        record.last_seen = utc_now()

        LOGGER.info(
            "Accepted BootNotification from %s (%s %s)",
            self.id,
            charging_station.get("vendor_name", "unknown vendor"),
            charging_station.get("model", "unknown model"),
        )

        return call_result.BootNotification(
            current_time=utc_now(),
            interval=self.heartbeat_interval,
            status=RegistrationStatusEnumType.accepted,
        )

    @on(Action.heartbeat)
    def on_heartbeat(self, **_: Any) -> call_result.Heartbeat:
        record = self.state.station(self.id)
        record.heartbeat_count += 1
        record.last_seen = utc_now()
        LOGGER.info("Heartbeat from %s", self.id)

        return call_result.Heartbeat(current_time=utc_now())

    @on(Action.status_notification)
    def on_status_notification(
        self,
        timestamp: str,
        connector_status: str,
        evse_id: int,
        connector_id: int,
        **_: Any,
    ) -> call_result.StatusNotification:
        record = self.state.station(self.id)
        record.last_seen = utc_now()
        record.status_notifications.append(
            {
                "timestamp": timestamp,
                "connector_status": connector_status,
                "evse_id": evse_id,
                "connector_id": connector_id,
            }
        )
        LOGGER.info(
            "Status from %s: EVSE %s connector %s is %s",
            self.id,
            evse_id,
            connector_id,
            connector_status,
        )

        return call_result.StatusNotification()

    @on(Action.transaction_event)
    def on_transaction_event(
        self,
        event_type: str,
        timestamp: str,
        trigger_reason: str,
        seq_no: int,
        transaction_info: dict[str, Any],
        **kwargs: Any,
    ) -> call_result.TransactionEvent:
        record = self.state.station(self.id)
        record.last_seen = utc_now()
        record.transaction_events.append(
            {
                "event_type": event_type,
                "timestamp": timestamp,
                "trigger_reason": trigger_reason,
                "seq_no": seq_no,
                "transaction_info": transaction_info,
                "meter_value": kwargs.get("meter_value"),
            }
        )
        LOGGER.info(
            "TransactionEvent from %s: %s transaction=%s seq=%s",
            self.id,
            event_type,
            transaction_info.get("transaction_id", "unknown"),
            seq_no,
        )

        return call_result.TransactionEvent()


class CentralSystem:
    """Accept and track OCPP charging-station connections."""

    def __init__(
        self,
        state: CentralSystemState | None = None,
        heartbeat_interval: int = 10,
    ) -> None:
        if heartbeat_interval < 1:
            raise ValueError("heartbeat_interval must be at least 1 second")
        self.state = state or CentralSystemState()
        self.heartbeat_interval = heartbeat_interval
        self.connections: dict[str, CentralSystemChargePoint] = {}

    async def on_connect(self, websocket: Any) -> None:
        if websocket.subprotocol != OCPP_SUBPROTOCOL:
            requested = websocket.request.headers.get(
                "Sec-WebSocket-Protocol", "none"
            )
            LOGGER.warning(
                "Rejected connection with subprotocol %s (requested %s)",
                websocket.subprotocol,
                requested,
            )
            await websocket.close(code=1002, reason="OCPP 2.0.1 is required")
            return

        charge_point_id = extract_charge_point_id(websocket.request.path)
        if not charge_point_id:
            LOGGER.warning("Rejected connection without a charge point ID")
            await websocket.close(code=1008, reason="Missing charge point ID")
            return

        charge_point = CentralSystemChargePoint(
            charge_point_id,
            websocket,
            self.state,
            self.heartbeat_interval,
        )
        self.connections[charge_point_id] = charge_point
        self.state.set_connected(charge_point_id, True)
        LOGGER.info("Charging station connected: %s", charge_point_id)

        try:
            await charge_point.start()
        except ConnectionClosed:
            LOGGER.info("Charging station disconnected: %s", charge_point_id)
        finally:
            if self.connections.get(charge_point_id) is charge_point:
                self.connections.pop(charge_point_id, None)
                self.state.set_connected(charge_point_id, False)


async def start_server(
    host: str = "0.0.0.0",
    port: int = 9000,
    *,
    state: CentralSystemState | None = None,
    heartbeat_interval: int = 10,
) -> tuple[Any, CentralSystem]:
    """Start a CSMS server and return it with its in-memory system state."""

    central_system = CentralSystem(
        state=state,
        heartbeat_interval=heartbeat_interval,
    )
    server = await websockets.serve(
        central_system.on_connect,
        host,
        port,
        subprotocols=[OCPP_SUBPROTOCOL],
        ping_interval=20,
        ping_timeout=20,
    )
    return server, central_system


async def serve_forever(
    host: str = "0.0.0.0",
    port: int = 9000,
    heartbeat_interval: int = 10,
) -> None:
    server, _ = await start_server(
        host,
        port,
        heartbeat_interval=heartbeat_interval,
    )
    LOGGER.info(
        "OCPP 2.0.1 Central System listening on ws://%s:%s",
        host,
        port,
    )
    await server.wait_closed()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--heartbeat-interval", type=int, default=10)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(
        serve_forever(
            host=args.host,
            port=args.port,
            heartbeat_interval=args.heartbeat_interval,
        )
    )


if __name__ == "__main__":
    main()
