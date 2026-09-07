"""Asyncio TCP client that simulates an EV connecting to a charger."""

from __future__ import annotations

import asyncio
import logging

LOGGER = logging.getLogger("project25.ev")


async def run_ev_session(
    charger_host: str,
    charger_port: int,
    charge_duration: float = 30.0,
) -> None:
    reader, writer = await asyncio.open_connection(charger_host, charger_port)
    LOGGER.info("EV connected to charger at %s:%s", charger_host, charger_port)

    try:
        writer.write(b"PLUG_IN\n")
        await writer.drain()
        LOGGER.info("EV sent PLUG_IN")

        await asyncio.sleep(charge_duration)

        writer.write(b"UNPLUG\n")
        await writer.drain()
        LOGGER.info("EV sent UNPLUG")
    finally:
        writer.close()
        await writer.wait_closed()
        LOGGER.info("EV disconnected from charger")


async def run_forever(
    charger_host: str,
    charger_port: int,
    charge_duration: float,
    session_interval: float,
) -> None:
    while True:
        try:
            await run_ev_session(charger_host, charger_port, charge_duration)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("EV session failed; retrying in %.1fs", session_interval)
        await asyncio.sleep(session_interval)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--charger-host", default="10.42.0.222")
    parser.add_argument("--charger-port", type=int, default=65432)
    parser.add_argument("--charge-duration", type=float, default=30.0)
    parser.add_argument("--session-interval", type=float, default=60.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_forever(
        args.charger_host,
        args.charger_port,
        args.charge_duration,
        args.session_interval,
    ))


if __name__ == "__main__":
    main()
