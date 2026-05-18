#!/usr/bin/env python3
"""
run_remote.py
Connects to a Raspberry Pi over SSH and runs a Python script on it.
Requires: pip install paramiko
"""

import paramiko
import sys
import getpass

# ── Configuration ────────────────────────────────────────────────────────────
REMOTE_HOST    = "192.168.1.100"           # IP or hostname of the target Pi
REMOTE_USER    = "pi"                      # SSH username
REMOTE_SCRIPT  = "/home/pi/myscript.py"   # Absolute path to the script on the Pi
PYTHON_BIN     = "python3"                # Python binary on the remote Pi
# ─────────────────────────────────────────────────────────────────────────────


def run_remote_script(
    host: str,
    user: str,
    password: str,
    script_path: str,
    python_bin: str = "python3",
    script_args: list[str] | None = None,
) -> int:
    """
    SSH into `host` and execute `script_path` with `python_bin`.

    Returns the remote process exit code.
    """
    args_str = " ".join(script_args) if script_args else ""
    command = f"{python_bin} {script_path} {args_str}".strip()

    client = paramiko.SSHClient()
    # Automatically accept the host key the first time (safe on a private LAN).
    # Replace with paramiko.RejectPolicy() + a known_hosts file for stricter security.
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

        stdin, stdout, stderr = client.exec_command(command)

        # Stream stdout in real time
        for line in iter(stdout.readline, ""):
            print(f"[remote] {line}", end="")

        # Print any errors
        err = stderr.read().decode()
        if err:
            print(f"[remote stderr]\n{err}", file=sys.stderr)

        exit_code = stdout.channel.recv_exit_status()
        print(f"[*] Remote script exited with code {exit_code}")
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
    # Prompt for password at runtime so it's never stored in the script
    password = getpass.getpass(f"SSH password for {REMOTE_USER}@{REMOTE_HOST}: ")

    # Optional: pass extra args to the remote script from the command line
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