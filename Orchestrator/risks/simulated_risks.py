"""
simulated_risks.py

Placeholder methods that simulate security risks for the EV charging testbed.
These functions still need to be filled in with experiment-specific behavior 
(network emulation, insecure defaults, injection vectors).

Keep these small and explicit so tests and orchestration can call them.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def emulate_open_telnet_port(host: str = "0.0.0.0", port: int = 23) -> None:
    """Placeholder: an exposed Telnet service on `host:port`

    Intended behavior: start a server that accepts unauthenticated
    connections or simulates banner messages
    """
    logger.info("Placeholder: emulate_open_telnet_port(%s, %d)", host, port)
    raise NotImplementedError("emulate_open_telnet_port is a placeholder")


def emulate_default_credentials(device_id: str | None = None) -> None:
    """Placeholder: a device using well-known default credentials

    Intended behavior: attempt to authenticate to other services using a small
    default-credential dictionary, or expose credentials in a config file
    """
    logger.info("Placeholder: emulate_default_credentials(%s)", device_id)
    raise NotImplementedError("emulate_default_credentials is a placeholder")


def emulate_unencrypted_traffic(endpoint: str | None = None) -> None:
    """Placeholder: sending sensitive data over unencrypted channels

    Intended behavior: send or log data without TLS, or replay captured traffic
    """
    logger.info("Placeholder: emulate_unencrypted_traffic(%s)", endpoint)
    raise NotImplementedError("emulate_unencrypted_traffic is a placeholder")


def emulate_command_injection(payload: str = "; rm -rf /") -> None:
    """Placeholder: a command-injection vector on a vulnerable API.

    Intended behavior: craft bad request payload and send it to a local test
    server that executes shell commands. DO NOT run destructive payloads
    """
    logger.info("Placeholder: emulate_command_injection(payload=%r)", payload)
    raise NotImplementedError("emulate_command_injection is a placeholder")


def run_all() -> None:
    """Run all placeholders in a non-destructive dry-run manner.

    Each function currently raises NotImplementedError; this runner demonstrates
    how orchestration code can call them and handle unimplemented features.
    """
    functions = [
        emulate_open_telnet_port,
        emulate_default_credentials,
        emulate_unencrypted_traffic,
        emulate_command_injection,
    ]

    for fn in functions:
        try:
            logger.info("Calling %s()", fn.__name__)
            fn()  # type: ignore[arg-type]
        except NotImplementedError as e:
            logger.warning("%s: %s", fn.__name__, e)
        except Exception as e:  # pragma: no cover - unexpected runtime errors
            logger.error("%s raised unexpected exception: %s", fn.__name__, e)


if __name__ == "__main__":
    run_all()
