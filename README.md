# Project 25 EV charging testbed

This repository currently implements the first OCPP milestone for the
seven-Raspberry-Pi testbed: two simulated charging stations connect to one
OCPP 2.0.1 Central System Management System (CSMS).

## Raspberry Pi assignments

| Pi | IP | Current role |
| --- | --- | --- |
| dongle-rp1 | 10.42.0.222 | Charging Station 1 (`CHARGER_01`) |
| dongle-rp2 | 10.42.0.167 | EV Simulator 1 |
| dongle-rp3 | 10.42.0.215 | Charging Station 2 (`CHARGER_02`) |
| dongle-rp4 | 10.42.0.110 | EV Simulator 2 |
| dongle-rp5 | 10.42.0.69 | OCPP Central System |
| dongle-rp6 | 10.42.0.83 | Reserved for grid, observability, or payment |
| dongle-rp7 | 10.42.0.1 | Router and orchestrator |

The EV simulators don't use OCPP. OCPP runs only between each charging
station and the CSMS. The existing TCP scripts remain available for the
EV-to-charger proof of concept until ISO 15118 is introduced.

## Install

Run this on RP1, RP3, RP5, and on a development machine used for tests:

```bash
cd /home/admin/dongle-warrior-bakery
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run the first OCPP milestone

Start the CSMS on RP5 first:

```bash
python3 main.py
```

Then run the same command on RP1 and RP3:

```bash
python3 main.py
```

`main.py` selects the service from `config/<hostname>.json`. For local
testing, hostname detection can be overridden:

```bash
python3 main.py --hostname dongle-rp5
python3 main.py --hostname dongle-rp1
python3 main.py --hostname dongle-rp3
```

The expected RP5 logs show both charge point IDs, accepted boot
notifications, `Available` status notifications, and recurring heartbeats.

The services may also be started directly:

```bash
python3 -m CSMS.server --host 0.0.0.0 --port 9000
python3 -m EV_Charger.ocpp_client --id CHARGER_01 --csms ws://10.42.0.69:9000
python3 -m EV_Charger.ocpp_client --id CHARGER_02 --csms ws://10.42.0.69:9000
```

## Start the OCPP fleet from RP7

Configure SSH keys and known-host entries from RP7 to RP1, RP3, and RP5.
The orchestrator intentionally rejects unknown SSH host keys.

After installing the project dependencies on those three destination Pis,
run this on RP7:

```bash
python3 Orchestrator/run_ocpp_fleet.py
```

It starts RP5 first, waits for the CSMS to remain running, then starts the
two charging stations. Press `Ctrl+C` on RP7 to stop all three processes.
If keys aren't configured yet, `--ask-password` prompts without storing the
password in the repository.

## Test locally

The integration test starts a temporary CSMS and connects two real OCPP
clients to it. Each client sends `BootNotification`, `StatusNotification`,
and `Heartbeat` messages.

```bash
python3 -m unittest -v tests.test_ocpp_integration
```

## Next milestone

After both charging stations remain connected reliably, convert the
EV-facing TCP server to `asyncio` and translate its events into OCPP
`StatusNotification` and `TransactionEvent` messages. Payment and account
authorization are intentionally out of scope for this milestone.
