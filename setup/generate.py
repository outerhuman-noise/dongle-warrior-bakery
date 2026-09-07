#!/usr/bin/env python3
"""
setup/generate.py

Unified setup script for dongle-warrior-bakery. Installs dependencies and
generates role-specific config/cert files, writing them into the EV/ or
EV_Charger/ folder depending on --role, rather than scattering setup output
across the repo root.

Assumes this script lives at <repo_root>/setup/generate.py, and that the
repo has already been cloned/pulled onto the Pi via git.

Usage (on the EV Pi):
    python3 setup/generate.py --role ev --interface eth0 --tcp-port 49154 --udp-port 49153

Usage (on the charger Pi):
    python3 setup/generate.py --role charger --interface eth0 --tcp-port 49152

NOTE: This assumes generic config keys (interface/ports/virtual_mode) similar
to what we used for the ISO15118-20 EDF-Lab flow. If your EV/EV_Charger
folders use different config filenames or an OCPP-specific config schema,
tell me the actual filenames/keys and I'll adjust write_config() to match.
"""

import argparse
import configparser
import subprocess
import sys
import os

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ROLE_DIRS = {
    "ev": os.path.join(REPO_DIR, "EV"),
    "charger": os.path.join(REPO_DIR, "EV_Charger"),
}

ROLE_CONFIG_FILENAMES = {
    "ev": "ev_config.ini",
    "charger": "charger_config.ini",
}


def run(cmd, cwd=None, check=True):
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=check)


def list_interfaces():
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, check=True).stdout
        print(out)
    except FileNotFoundError:
        out = subprocess.run(["ip", "a"], capture_output=True, text=True, check=True).stdout
        print(out)


def apt_install(packages):
    run(["sudo", "apt-get", "update"])
    run(["sudo", "apt-get", "install", "-y"] + packages)


def pull_repo():
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        sys.exit(
            f"{REPO_DIR} doesn't look like a git repo. "
            f"Clone it first with `git clone <your-repo-url>` before running this script."
        )
    print(f"Pulling latest changes in {REPO_DIR}...")
    run(["git", "pull"], cwd=REPO_DIR)


def install_python_deps():
    req_file = os.path.join(REPO_DIR, "requirements.txt")
    if os.path.isfile(req_file):
        run([sys.executable, "-m", "pip", "install", "-r", req_file])
    else:
        print(f"WARNING: {req_file} not found, skipping pip install.")


def ensure_role_dir(role):
    role_dir = ROLE_DIRS[role]
    os.makedirs(role_dir, exist_ok=True)
    return role_dir


def write_config(role, interface, tcp_port, udp_port, virtual_mode):
    role_dir = ensure_role_dir(role)
    config_path = os.path.join(role_dir, ROLE_CONFIG_FILENAMES[role])

    config = configparser.ConfigParser()
    config.optionxform = str
    if os.path.isfile(config_path):
        config.read(config_path)

    if "NETWORK" not in config:
        config["NETWORK"] = {}
    config["NETWORK"]["interface"] = interface
    config["NETWORK"]["tcp_port"] = str(tcp_port)
    if role == "ev":
        config["NETWORK"]["udp_port"] = str(udp_port)

    if "SETTINGS" not in config:
        config["SETTINGS"] = {}
    config["SETTINGS"]["virtual_mode"] = str(virtual_mode).lower()

    with open(config_path, "w") as f:
        config.write(f)

    print(f"Wrote config to {config_path}:")
    for section in config.sections():
        print(f"  [{section}]")
        for key, val in config[section].items():
            print(f"    {key} = {val}")

    return config_path


def generate_certs(role):
    role_dir = ensure_role_dir(role)
    certs_dir = os.path.join(role_dir, "certs")
    os.makedirs(certs_dir, exist_ok=True)

    gen_script = os.path.join(REPO_DIR, "shared", "certificates", "generateCertificates.sh")
    if os.path.isfile(gen_script):
        run(["sh", gen_script, certs_dir])
    else:
        print(
            f"NOTE: no cert-generation script found at {gen_script}. "
            f"Created empty certs dir at {certs_dir} — point me to your actual "
            f"cert generation logic (e.g. under CSMS/ or config/) and I'll wire it in."
        )


def main():
    parser = argparse.ArgumentParser(description="Generate EV/EV_Charger setup, writing outputs into their own folders.")
    parser.add_argument("--role", required=True, choices=["ev", "charger"], help="Which side to set up")
    parser.add_argument("--interface", help="Network interface connecting the two Pis (e.g. eth0, wlan0)")
    parser.add_argument("--tcp-port", type=int, default=None, help="TCP port (49152-65535)")
    parser.add_argument("--udp-port", type=int, default=None, help="UDP port for EV role only (49152-65535)")
    parser.add_argument("--virtual-mode", action="store_true", default=True, help="Simulate comms card in software")
    parser.add_argument("--skip-install", action="store_true",
                         help="Skip pip install step (use on your PC, since Pi deps are arch-specific)")
    parser.add_argument("--skip-generate", action="store_true",
                         help="Skip writing config/certs (use on the Pi, if these were already generated on your PC and committed to the repo)")
    parser.add_argument("--skip-pull", action="store_true",
                         help="Skip git pull (useful if you're running this from an uncommitted working copy on your PC)")
    args = parser.parse_args()

    default_tcp = {"ev": 49154, "charger": 49152}[args.role]
    tcp_port = args.tcp_port or default_tcp
    udp_port = args.udp_port or 49153

    for name, port in (("tcp-port", tcp_port), ("udp-port", udp_port)):
        if not (49152 <= port <= 65535):
            sys.exit(f"{name} must be between 49152 and 65535.")

    if not args.skip_pull:
        pull_repo()

    if not args.skip_install:
        install_python_deps()

    if not args.skip_generate:
        interface = args.interface
        if not interface:
            print("No --interface given. Here are your current interfaces:")
            list_interfaces()
            interface = input("Enter the interface name to use (the one the OTHER Pi will connect over): ").strip()
            if not interface:
                sys.exit("An interface name is required.")
        write_config(args.role, interface, tcp_port, udp_port, args.virtual_mode)
        generate_certs(args.role)
    else:
        print("Skipping config/cert generation (--skip-generate). Using whatever is already committed in the repo.")

    role_dir = ROLE_DIRS[args.role]
    print(f"\nDone. All {args.role} outputs are under: {role_dir}")


if __name__ == "__main__":
    main()