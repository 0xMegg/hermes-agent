"""Shared gateway restart constants and parsing helpers."""

from __future__ import annotations

import os
from typing import Literal, Optional

from hermes_cli.config import DEFAULT_CONFIG

# EX_TEMPFAIL from sysexits.h — used to ask the service manager to restart
# the gateway after a graceful drain/reload path completes.
GATEWAY_SERVICE_RESTART_EXIT_CODE = 75

DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT = float(
    DEFAULT_CONFIG["agent"]["restart_drain_timeout"]
)

ServiceManager = Literal["systemd", "launchd"]


def detect_service_manager() -> Optional[ServiceManager]:
    """Return the service manager that launched this process, if any.

    This must be based on manager-provided environment, not just the host OS:
    users can run ``hermes gateway run`` manually on macOS/Linux, and in that
    case an in-process ``/restart`` must use the detached fallback rather than
    exiting with the service-restart code and waiting for a supervisor that
    does not exist.
    """
    if os.environ.get("INVOCATION_ID"):
        return "systemd"
    # launchd sets XPC_SERVICE_NAME for LaunchAgent/LaunchDaemon children; in
    # normal terminals it is usually absent or set to an interactive shell-ish
    # value such as "0". Treat the Hermes launchd label as the reliable signal.
    xpc_service_name = os.environ.get("XPC_SERVICE_NAME", "")
    if xpc_service_name.startswith("ai.hermes."):
        return "launchd"
    return None


def parse_restart_drain_timeout(raw: object) -> float:
    """Parse a configured drain timeout, falling back to the shared default."""
    try:
        raw_text = str(raw or "").strip()
        value = float(raw_text) if raw_text else DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_GATEWAY_RESTART_DRAIN_TIMEOUT
    return max(0.0, value)
