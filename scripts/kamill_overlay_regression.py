#!/usr/bin/env python3
"""Run Kamill overlay regression tests after Hermes upstream updates.

This script intentionally mirrors kamill_overlay_manifest.yaml so operators can
run one stable command after `hermes update` or an upstream rebase.
"""

from __future__ import annotations

import subprocess
import sys


TESTS = [
    "tests/tools/test_approval.py::TestApprovalTimeoutIsNotConsent",
    "tests/tools/test_execute_code_approval_cluster.py::test_guard_gateway_timeout_blocks",
    "tests/gateway/test_discord_approval_dm.py",
    "tests/gateway/test_discord_slash_auth.py",
    "tests/gateway/test_discord_slash_commands.py",
    "tests/gateway/test_discord_connect.py",
]


def main() -> int:
    cmd = ["uv", "run", "pytest", "-o", "addopts=", *TESTS, "-q"]
    print("Running Kamill overlay regression suite:", flush=True)
    print(" ".join(cmd), flush=True)
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
