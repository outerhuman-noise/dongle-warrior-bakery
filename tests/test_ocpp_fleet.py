"""Unit tests for the RP7 OCPP fleet and smoke-test command builder."""

import unittest

from Orchestrator.run_ocpp_fleet import (
    CommandResult,
    build_smoke_command,
    certificate_stem,
    find_service,
    normalize_csms_url,
    smoke_test_passed,
)


class OcppFleetScriptTest(unittest.TestCase):
    def test_find_service_uses_inventory_name(self) -> None:
        inventory = {
            "services": [
                {
                    "name": "charger-01",
                    "host": "10.42.0.222",
                    "charge_point_id": "CHARGER_01",
                }
            ]
        }
        self.assertEqual(find_service(inventory, "charger-01")["host"], "10.42.0.222")

    def test_certificate_stem_matches_generated_testbed_names(self) -> None:
        self.assertEqual(certificate_stem("CHARGER_01"), "charger1")
        self.assertEqual(certificate_stem("CHARGER_02"), "charger2")

    def test_plain_command_runs_one_shot_charger(self) -> None:
        command = build_smoke_command(
            repo_dir="/home/admin/dongle-warrior-bakery",
            charger_id="CHARGER_01",
            csms_url="ws://10.42.0.69:9000",
            tls=False,
            cert_stem="charger1",
        )

        self.assertIn("EV_Charger.ocpp_client", command)
        self.assertIn("--heartbeat-limit 1", command)
        self.assertNotIn("--tls", command)

    def test_tls_command_uses_generated_certificate_names(self) -> None:
        command = build_smoke_command(
            repo_dir="/home/admin/dongle-warrior-bakery",
            charger_id="CHARGER_01",
            csms_url="wss://10.42.0.69:9000",
            tls=True,
            cert_stem="charger1",
        )

        self.assertIn("--tls", command)
        self.assertIn("certs/charger1.crt", command)
        self.assertIn("certs/charger1.key", command)
        self.assertIn("certs/ca.crt", command)

    def test_tls_option_upgrades_default_url_scheme(self) -> None:
        self.assertEqual(
            normalize_csms_url("ws://10.42.0.69:9000", tls=True),
            "wss://10.42.0.69:9000",
        )

    def test_result_requires_exit_zero_and_both_markers(self) -> None:
        result = CommandResult(
            0,
            "CHARGER_01 accepted by Central System\n"
            "Heartbeat acknowledged for CHARGER_01\n",
        )
        self.assertTrue(smoke_test_passed(result))
        self.assertFalse(smoke_test_passed(CommandResult(1, result.output)))
        self.assertFalse(smoke_test_passed(CommandResult(0, "Heartbeat acknowledged")))


if __name__ == "__main__":
    unittest.main()
