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
