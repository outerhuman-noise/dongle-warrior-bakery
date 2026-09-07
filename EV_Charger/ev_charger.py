"""Asyncio TCP server that receives EV plug-in/unplug signals and triggers OCPP sessions."""

from __future__ import annotations

import asyncio
from functools import partial
import logging

LOGGER = logging.getLogger("project25.ev_charger")

EV_PORT = 65432


async def handle_ev_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    station: object,
    session_duration: float,
    tx_id_counter: list[int],
) -> None:
    peer = writer.get_extra_info("peername")
    LOGGER.info("EV connected from %s", peer)

    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            message = line.decode().strip()
            LOGGER.info("Received from EV: %s", message)

            if message == "PLUG_IN":
                tx_id_counter[0] += 1
                tx_id = f"{station.id}-TX-{tx_id_counter[0]}"
                asyncio.create_task(station.simulate_charging_session(tx_id, session_duration))
            elif message == "UNPLUG":
                LOGGER.info("EV unplugged from %s", station.id)
            else:
                LOGGER.warning("Unknown message from EV: %s", message)
    finally:
        writer.close()
        LOGGER.info("EV disconnected from %s", peer)


async def start_ev_server(
    station: object,
    session_duration: float,
    host: str = "0.0.0.0",
    port: int = EV_PORT,
) -> asyncio.Server:
    tx_id_counter = [0]
    handler = partial(
        handle_ev_connection,
        station=station,
        session_duration=session_duration,
        tx_id_counter=tx_id_counter,
    )
    server = await asyncio.start_server(handler, host, port)
    LOGGER.info("EV-facing TCP server listening on %s:%s", host, port)
    return server
