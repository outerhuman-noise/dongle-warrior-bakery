"""Local end-to-end test for two chargers and one OCPP Central System."""

import asyncio
from contextlib import suppress
import unittest

import websockets

from CSMS.server import CentralSystemState, start_server
from EV_Charger.ocpp_client import ChargerSettings, SimulatedChargingStation, run_session

OCPP_SUBPROTOCOL = "ocpp2.0.1"


class TwoChargerIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.state = CentralSystemState()
        self.server, _ = await start_server(
            "127.0.0.1",
            0,
            state=self.state,
            heartbeat_interval=1,
        )
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def test_two_chargers_boot_report_status_and_heartbeat(self) -> None:
        csms_url = f"ws://127.0.0.1:{self.port}"
        chargers = [
            ChargerSettings("CHARGER_01", csms_url),
            ChargerSettings("CHARGER_02", csms_url),
        ]

        await asyncio.gather(
            *(run_session(charger, heartbeat_limit=1) for charger in chargers)
        )

        self.assertEqual(
            set(self.state.stations),
            {"CHARGER_01", "CHARGER_02"},
        )

        for charge_point_id in ("CHARGER_01", "CHARGER_02"):
            record = self.state.stations[charge_point_id]
            self.assertEqual(record.boot_count, 1)
            self.assertEqual(record.heartbeat_count, 1)
            self.assertEqual(len(record.status_notifications), 1)
            self.assertEqual(
                record.status_notifications[0]["connector_status"],
                "Available",
            )


    async def test_charger_completes_charging_session(self) -> None:
        csms_url = f"ws://127.0.0.1:{self.port}"
        settings = ChargerSettings(
            "CHARGER_01",
            csms_url,
            session_duration=0.1,
        )

        async with websockets.connect(
            settings.websocket_url,
            subprotocols=[OCPP_SUBPROTOCOL],
            ping_interval=20,
            ping_timeout=20,
            proxy=None,
        ) as websocket:
            station = SimulatedChargingStation(settings.charge_point_id, websocket)
            listener = asyncio.create_task(station.start())
            try:
                await station.send_boot_notification(settings.vendor_name, settings.model)
                await station.simulate_charging_session("CHARGER_01-TX-1", settings.session_duration)
            finally:
                listener.cancel()
                with suppress(asyncio.CancelledError):
                    await listener

        record = self.state.stations["CHARGER_01"]
        self.assertEqual(len(record.transaction_events), 2)
        started, ended = record.transaction_events
        self.assertEqual(started["seq_no"], 0)
        self.assertEqual(ended["seq_no"], 1)
        self.assertEqual(
            started["transaction_info"]["transaction_id"], "CHARGER_01-TX-1"
        )
        self.assertEqual(
            ended["transaction_info"]["transaction_id"], "CHARGER_01-TX-1"
        )


if __name__ == "__main__":
    unittest.main()

