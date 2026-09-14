"""Harness-agnostic diagnostics for local configuration and optional Rapid7 access."""

import asyncio
import sys
from importlib.metadata import version
from typing import IO, Any, Callable

import httpx

from .config import Settings
from .onboarding import verify_credentials


def run_doctor(
    *,
    online: bool = False,
    output: IO[str] = sys.stdout,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: Callable[[Any], Any] = asyncio.run,
) -> int:
    """Run safe diagnostics; network access is opt-in through ``online``."""
    print("Rapid7 InsightConnect MCP doctor\n", file=output)
    print(f"Runtime\n  ✓ Version {version('rapid7-insightconnect-mcp')}", file=output)

    try:
        settings = Settings.load()
    except ValueError as error:
        print("\nConfiguration", file=output)
        print(f"  ✗ {error}", file=output)
        print("\nResult: configuration required", file=output)
        return 1

    print("\nConfiguration", file=output)
    print("  ✓ Credentials configured", file=output)
    print(f"  ✓ Region: {settings.region}", file=output)
    writes = "enabled" if settings.allow_writes else "disabled"
    print(f"  ✓ Writes {writes}", file=output)

    print("\nRapid7 connectivity", file=output)
    if not online:
        print("  ○ Not checked", file=output)
        print("    Run `rapid7-insightconnect-mcp doctor --online`", file=output)
        print("\nResult: healthy local configuration", file=output)
        return 0

    failure = runner(verify_credentials(settings, transport))
    if failure:
        print(f"  ✗ Read-only API check failed: {failure}", file=output)
        print("\nResult: Rapid7 check failed", file=output)
        return 1

    print("  ✓ Read-only API check succeeded", file=output)
    print("\nResult: healthy", file=output)
    return 0
