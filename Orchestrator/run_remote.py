#!/usr/bin/env python3
"""
run_remote.py
Connects to a Raspberry Pi over SSH and runs a Python script on it.
Stops the remote script cleanly when this script is interrupted (Ctrl+C).
Requires: pip install paramiko
"""

import paramiko
import sys
import getpass
import signal

# ── Configuration ────────────────────────────────────────────────────────────
REMOTE_HOST   = "10.42.0.222"
REMOTE_USER   = "dongle-rp1"
REMOTE_SCRIPT = "/home/admin/dongle-warrior-bakery/EV_Charger/test_server.py"
PYTHON_BIN    = "python3"
# ─────────────────────────────────────────────────────────────────────────────


def run_remote_script(
    host: str,
    user: str,
    password: str,
    script_path: str,
    python_bin: str = "python3",
    script_args: list[str] | None = None,
) -> int:
    args_str = " ".join(script_args) if script_args else ""
    command = f"{python_bin} {script_path} {args_str}".strip()

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"[*] Connecting to {user}@{host} …")
        client.connect(
            hostname=host,
            username=user,
            password=password,
            timeout=10,
        )
        print(f"[*] Running: {command}")
        print(f"[*] Press Ctrl+C to stop the remote script and exit.\n")

        transport = client.get_transport()
        channel = transport.open_session()
        channel.get_pty()          # allocate a pseudo-terminal so Ctrl+C signals propagate
        channel.exec_command(command)

        def _stop(sig, frame):
            print("\n[*] Interrupted — sending SIGINT to remote script …")
            channel.send("\x03")   # send Ctrl+C down the pty
            channel.close()
            client.close()
            print("[*] Remote script stopped. Exiting.")
            sys.exit(0)

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        # Stream output until the remote process exits
        while not channel.exit_status_ready():
            if channel.recv_ready():
                data = channel.recv(1024).decode(errors="replace")
                print(data, end="", flush=True)

        # Drain any remaining output
        while channel.recv_ready():
            data = channel.recv(1024).decode(errors="replace")
            print(data, end="", flush=True)

        exit_code = channel.recv_exit_status()
        print(f"\n[*] Remote script exited with code {exit_code}")
        return exit_code

    except paramiko.AuthenticationException:
        print("[!] Authentication failed — check your username and password.", file=sys.stderr)
        return 1
    except paramiko.SSHException as e:
        print(f"[!] SSH error: {e}", file=sys.stderr)
        return 1
    except TimeoutError:
        print(f"[!] Connection to {host} timed out.", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    password = getpass.getpass(f"SSH password for {REMOTE_USER}@{REMOTE_HOST}: ")
    extra_args = sys.argv[1:]
    exit_code = run_remote_script(
        host=REMOTE_HOST,
        user=REMOTE_USER,
        password=password,
        script_path=REMOTE_SCRIPT,
        python_bin=PYTHON_BIN,
        script_args=extra_args,
    )
    sys.exit(exit_code)