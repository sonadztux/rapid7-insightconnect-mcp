"""Harness-agnostic diagnostics for local configuration and optional Rapid7 access."""

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import version
from typing import IO, Any

import httpx

from .config import ConfigurationSource, resolve_settings
from .onboarding import verify_credentials


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class DiagnosticCheck:
    section: str
    name: str
    status: CheckStatus
    message: str
    remediation: str | None = None


def _failure_check(failure: str) -> DiagnosticCheck:
    if "HTTP 401" in failure:
        return DiagnosticCheck(
            "Rapid7 connectivity",
            "rapid7-connectivity",
            CheckStatus.FAIL,
            "Authentication failed (HTTP 401)",
            "Check the API key and region.",
        )
    if "HTTP 403" in failure:
        return DiagnosticCheck(
            "Rapid7 connectivity",
            "rapid7-connectivity",
            CheckStatus.FAIL,
            "Authorization failed (HTTP 403)",
            "Check Rapid7 API key permissions.",
        )
    if "connection failed" in failure.lower():
        return DiagnosticCheck(
            "Rapid7 connectivity",
            "rapid7-connectivity",
            CheckStatus.FAIL,
            "Connection failed",
            "Check network access to the configured Rapid7 regional API endpoint.",
        )
    if "timed out" in failure.lower():
        return DiagnosticCheck(
            "Rapid7 connectivity",
            "rapid7-connectivity",
            CheckStatus.FAIL,
            "Request timed out",
            "Check network access and try the read-only diagnostic again.",
        )
    return DiagnosticCheck(
        "Rapid7 connectivity",
        "rapid7-connectivity",
        CheckStatus.FAIL,
        f"Read-only API check failed: {failure}",
    )


def collect_diagnostics(
    *,
    online: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: Callable[[Any], Any] = asyncio.run,
) -> list[DiagnosticCheck]:
    """Collect safe diagnostic facts without rendering them."""
    checks = [
        DiagnosticCheck(
            "Runtime",
            "version",
            CheckStatus.PASS,
            f"Version {version('rapid7-insightconnect-mcp')}",
        )
    ]

    resolution = resolve_settings()
    source_status = CheckStatus.PASS if resolution.settings is not None else CheckStatus.FAIL
    checks.append(
        DiagnosticCheck(
            "Configuration",
            "configuration-source",
            source_status,
            f"Source: {resolution.source.value}",
        )
    )
    if resolution.settings is None:
        checks.append(
            DiagnosticCheck(
                "Configuration",
                "configuration",
                CheckStatus.FAIL,
                resolution.error or "Rapid7 configuration is unavailable",
            )
        )
        return checks

    settings = resolution.settings
    checks.append(
        DiagnosticCheck(
            "Configuration",
            "credentials",
            CheckStatus.PASS,
            "Credentials configured",
        )
    )
    if resolution.source is ConfigurationSource.STORED:
        checks.append(
            DiagnosticCheck(
                "Configuration",
                "credential-storage",
                CheckStatus.PASS,
                "Credential storage validated",
            )
        )
    checks.extend(
        [
            DiagnosticCheck(
                "Configuration",
                "region",
                CheckStatus.PASS,
                f"Region: {settings.region}",
            ),
            DiagnosticCheck(
                "Configuration",
                "write-policy",
                CheckStatus.PASS,
                f"Writes {'enabled' if settings.allow_writes else 'disabled'}",
            ),
        ]
    )

    if not online:
        checks.append(
            DiagnosticCheck(
                "Rapid7 connectivity",
                "rapid7-connectivity",
                CheckStatus.WARN,
                "Not checked",
                "Run `rapid7-insightconnect-mcp doctor --online`",
            )
        )
        return checks

    failure = runner(verify_credentials(settings, transport))
    if failure:
        checks.append(_failure_check(failure))
    else:
        checks.append(
            DiagnosticCheck(
                "Rapid7 connectivity",
                "rapid7-connectivity",
                CheckStatus.PASS,
                "Read-only API check succeeded",
            )
        )
    return checks


def run_doctor(
    *,
    online: bool = False,
    output: IO[str] = sys.stdout,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: Callable[[Any], Any] = asyncio.run,
) -> int:
    """Render safe diagnostics; network access is opt-in through ``online``."""
    checks = collect_diagnostics(online=online, transport=transport, runner=runner)
    print("Rapid7 InsightConnect MCP doctor", file=output)

    current_section: str | None = None
    markers = {
        CheckStatus.PASS: "✓",
        CheckStatus.WARN: "○",
        CheckStatus.FAIL: "✗",
    }
    for check in checks:
        if check.section != current_section:
            print(f"\n{check.section}", file=output)
            current_section = check.section
        print(f"  {markers[check.status]} {check.message}", file=output)
        if check.remediation:
            print(f"    {check.remediation}", file=output)

    failures = [check for check in checks if check.status is CheckStatus.FAIL]
    if failures:
        configuration_failure = any(check.section == "Configuration" for check in failures)
        result = "configuration required" if configuration_failure else "Rapid7 check failed"
        print(f"\nResult: {result}", file=output)
        return 1

    if any(check.status is CheckStatus.WARN for check in checks):
        print("\nResult: healthy local configuration", file=output)
    else:
        print("\nResult: healthy", file=output)
    return 0
