"""Local end-to-end test for two chargers and one OCPP Central System."""

import asyncio
import unittest

from CSMS.server import CentralSystemState, start_server
from EV_Charger.ocpp_client import ChargerSettings, run_session


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


if __name__ == "__main__":
    unittest.main()

