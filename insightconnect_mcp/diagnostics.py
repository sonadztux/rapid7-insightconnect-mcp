"""Structured local checks with explicitly opted-in, read-only connectivity."""

import asyncio
import platform
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from itertools import groupby
from typing import IO, Literal

import httpx

from .config import ConfigurationSource, resolve_settings
from .onboarding import verify_credentials
from .storage import load_credentials


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    status: Literal["pass", "warn", "fail"]
    message: str
    remediation: str | None = None


def storage_check() -> DiagnosticCheck:
    try:
        stored = load_credentials()
    except (OSError, ValueError):
        return DiagnosticCheck(
            "storage",
            "fail",
            "Stored credentials are invalid or unsafe.",
            "Check JSON, regular file ownership, private permissions "
            "and trusted directory ancestry.",
        )
    if stored is None:
        return DiagnosticCheck("storage", "warn", "No credential file found.")
    return DiagnosticCheck(
        "storage",
        "pass",
        "Valid credential file: regular, current owner, private permissions, trusted ancestry.",
    )


async def diagnose(
    *,
    online: bool = False,
    environ: Mapping[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[DiagnosticCheck]:
    resolution = resolve_settings(environ)
    checks = [
        DiagnosticCheck(
            "runtime",
            "pass",
            f"Version {version('rapid7-insightconnect-mcp')}; Python {platform.python_version()}",
        )
    ]
    settings = resolution.settings
    if settings is None:
        checks.append(
            DiagnosticCheck(
                "configuration",
                "fail",
                f"Rapid7 not configured. {resolution.error}",
                "Call setup or run `uvx rapid7-insightconnect-mcp configure`.",
            )
        )
    else:
        writes = "enabled" if settings.allow_writes else "disabled"
        checks.append(
            DiagnosticCheck(
                "configuration",
                "pass",
                f"Credentials configured. Source: {resolution.source.value}; "
                f"Region: {settings.region}; Writes {writes}",
            )
        )
    checks.append(storage_check())
    if resolution.source == ConfigurationSource.ENVIRONMENT:
        checks.append(
            DiagnosticCheck(
                "environment",
                "warn",
                "R7_* environment settings override stored credentials.",
                "Remove all R7_API_KEY, R7_REGION and R7_ALLOW_WRITES overrides "
                "to use stored settings.",
            )
        )
    else:
        checks.append(DiagnosticCheck("environment", "pass", "No R7_* configuration overrides."))
    if online and settings is not None:
        failure = await verify_credentials(settings, transport=transport)
        checks.append(
            DiagnosticCheck(
                "connectivity",
                "fail" if failure else "pass",
                failure or "Authentication accepted; read-only workflows request succeeded.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                "connectivity",
                "warn",
                "Not checked.",
                "Configure Rapid7 first, then run `rapid7-insightconnect-mcp doctor --online`.",
            )
        )
    return checks


SECTIONS = {
    "runtime": "Runtime",
    "configuration": "Configuration",
    "storage": "Credential storage",
    "environment": "Environment",
    "connectivity": "Rapid7 connectivity",
}
MARKERS = {"pass": "✓", "warn": "○", "fail": "✗"}


def run_doctor(*, online: bool = False, output: IO[str] | None = None) -> int:
    output = sys.stdout if output is None else output
    checks = asyncio.run(diagnose(online=online))
    print("Rapid7 InsightConnect MCP doctor", file=output)
    for section, group in groupby(checks, key=lambda check: SECTIONS[check.name]):
        print(f"\n{section}", file=output)
        for check in group:
            print(f"  {MARKERS[check.status]} {check.message}", file=output)
            if check.remediation:
                print(f"    {check.remediation}", file=output)
    failed = any(check.status == "fail" for check in checks)
    print(f"\nResult: {'needs attention' if failed else 'healthy'}", file=output)
    return int(failed)
