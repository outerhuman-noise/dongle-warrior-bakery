#!/usr/bin/env python3
"""
git_pull_fleet.py
Runs on dongle-rp7 (10.42.0.1) and SSHes into the other 6 RPis to
run `git pull` in /home/admin/dongle-warrior-bakery.
Requires: paramiko  →  pip install paramiko
"""

import paramiko

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME  = "admin"
PASSWORD  = "admin1*"
REPO_DIR  = "/home/admin/dongle-warrior-bakery"
GIT_CMD   = f"cd {REPO_DIR} && git pull"

HOSTS = [
    {"name": "dongle-rp1", "ip": "10.42.0.222"},
    {"name": "dongle-rp2", "ip": "10.42.0.167"},
    {"name": "dongle-rp3", "ip": "10.42.0.215"},
    {"name": "dongle-rp4", "ip": "10.42.0.110"},
    {"name": "dongle-rp5", "ip": "10.42.0.69"},   # labelled rp4 currently
    {"name": "dongle-rp6", "ip": "10.42.0.83"},
]
# ─────────────────────────────────────────────────────────────────────────────


def git_pull(host: dict) -> None:
    name, ip = host["name"], host["ip"]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"\n{'─'*50}")
        print(f"[{name}]  {ip}")
        print(f"{'─'*50}")

        client.connect(ip, username=USERNAME, password=PASSWORD, timeout=10)
        stdin, stdout, stderr = client.exec_command(GIT_CMD)

        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()

        if out:
            print(out)
        if err:
            print(f"[stderr] {err}")

    except Exception as e:
        print(f"  ERROR: {e}")
    finally:
        client.close()


if __name__ == "__main__":
    print(f"Starting git pull on {len(HOSTS)} hosts …")
    print(f"Repo: {REPO_DIR}\n")

    for host in HOSTS:
        git_pull(host)

    print(f"\n{'─'*50}")
    print("Done.")