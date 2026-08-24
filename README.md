# Dongle Warrior Bakery — IoT security testbed

This project uses Raspberry Pi devices to simulate an IoT system for testing security issues. The research context is an EV charging system where the Pi devices and associated software will act as chargers, orchestrators, and network interactions so we can exercise and evaluate attack surfaces, monitoring, and mitigation strategies.

# Fixing the `paramiko` import (Pylance: "could not be resolved")

This project uses `paramiko` for SSH connections in the orchestrator script [Orchestrator/ssh/run_remote.py](Orchestrator/ssh/run_remote.py#L1-L120).
The simulated risks placeholders live in [Orchestrator/risks/simulated_risks.py](Orchestrator/risks/simulated_risks.py#L1-L120).

If your editor (Pylance) reports "Import 'paramiko' could not be resolved from source", follow the steps below.

**Cause:** The language server is using a different Python interpreter than the one where `paramiko` is installed.

**Quick steps (recommended)**

- Ensure the workspace interpreter is your project's virtual environment (`.venv`).
  - Open Command Palette → `Python: Select Interpreter` and pick `.venv\Scripts\python.exe` (Windows) or `.venv/bin/python` (macOS/Linux).
- Install `paramiko` into that interpreter:

PowerShell / Windows:
```powershell
.venv\Scripts\python.exe -m pip install paramiko
```

macOS / Linux:
```bash
.venv/bin/python -m pip install paramiko
```

- Verify the installation:

PowerShell / Windows:
```powershell
.venv\Scripts\python.exe -c "import paramiko; print(paramiko.__version__)"
```

macOS / Linux:
```bash
.venv/bin/python -c 'import paramiko; print(paramiko.__version__)'
```

- Reload VS Code or restart the language server:
  - Command Palette → `Developer: Reload Window` or `Python: Restart Language Server`.

**Alternative (system Python)**

If you do not use a virtual environment and want to install globally:

```bash
python -m pip install paramiko
```

**Verify Pylance is using the same interpreter**

Run this in a terminal to ensure the `python` you use for pip is the same as the language server interpreter:

PowerShell / Windows:
```powershell
.venv\Scripts\python.exe -m pip list
```

macOS / Linux:
```bash
.venv/bin/python -m pip list
```

**Add to project dependencies**

To make this reproducible for others, add `paramiko` to `requirements.txt`:

```bash
echo paramiko==$(.venv\Scripts\python.exe -c "import paramiko; print(paramiko.__version__)") >> requirements.txt
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

(Adjust path to `.venv` if your venv location differs.)

**If the error persists**
- Confirm you installed `paramiko` into the exact interpreter used by VS Code.
- Check the Python path shown in the bottom-left of VS Code (or in the `Python: Select Interpreter` UI).
- Run the quick verification snippet above; if it prints the version, the runtime is fine — reloading the editor usually fixes the linting.

If you want, I can run the verification commands for you or update `requirements.txt` with an explicit `paramiko` pin.
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
