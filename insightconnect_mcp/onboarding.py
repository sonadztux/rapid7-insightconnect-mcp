"""Shared Rapid7 onboarding logic for the CLI `configure` command and the MCP setup tool.

The API key goes only to secure local storage and Rapid7: never printed, logged,
or placed in harness-specific configuration.
"""

import asyncio
import getpass as getpass_module
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, get_args

import httpx
from pydantic import SecretStr

from .client import ApiError, InsightConnectClient
from .config import Region, Settings
from .storage import save_credentials

REGIONS: tuple[str, ...] = get_args(Region)
KEY_ATTEMPTS = 3


class Aborted(Exception):
    """Raised when input is unavailable or the user supplies no credential."""


@dataclass(frozen=True)
class ConfigurationSummary:
    region: str
    writes_enabled: bool
    recommended_next_action: str


def summary_of(settings: Settings) -> ConfigurationSummary:
    return ConfigurationSummary(
        region=settings.region,
        writes_enabled=settings.allow_writes,
        recommended_next_action="list_workflows",
    )


async def verify_credentials(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> str | None:
    """Read-only probe using the secure client; returns only sanitized failures."""
    async with InsightConnectClient(settings, transport=transport) as client:
        try:
            await client.request("GET", "connect/v2/workflows", params={"limit": 1})
        except ApiError as error:
            return str(error)
    return None


def persist_settings(settings: Settings) -> Path:
    """Store credentials through the owner-only storage implementation."""
    return save_credentials(settings)


def ask(input_fn: Callable[[str], str], prompt: str) -> str:
    try:
        return input_fn(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise Aborted("Configuration needs an interactive terminal; run it from a shell") from None


def ask_yes_no(input_fn: Callable[[str], str], prompt: str, *, default: bool = False) -> bool:
    while True:
        answer = ask(input_fn, prompt).lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False


def read_key(getpass_fn: Callable[[str], str]) -> str:
    """Typed input must stay hidden; getpass only warns when it cannot disable echo."""
    prompt = "API key (input hidden): "
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass_module.GetPassWarning)
        return getpass_fn(prompt)


def ask_key(getpass_fn: Callable[[str], str], output: IO[str]) -> SecretStr:
    for _ in range(KEY_ATTEMPTS):
        try:
            key = read_key(getpass_fn).strip()
        except getpass_module.GetPassWarning:
            raise Aborted(
                "This terminal cannot keep the input hidden; run configure in a terminal that can"
            ) from None
        except (EOFError, KeyboardInterrupt):
            raise Aborted(
                "Configuration needs an interactive terminal; run it from a shell"
            ) from None
        if key:
            return SecretStr(key)
        print("  Empty input.", file=output)
    raise Aborted("Configuration received no API key")


def configure_interactively(
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass_module.getpass,
    output: IO[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Terminal configure flow: region, writes, key, optional read-only verification, save.

    A failed verification keeps any previously stored credential intact.
    """
    if output is None:
        output = sys.stdout
    print("Rapid7 InsightConnect MCP configuration\n", file=output)
    for index, region in enumerate(REGIONS, start=1):
        print(f"  {index}) {region}", file=output)
    try:
        while True:
            answer = ask(input_fn, "Region number [1]: ")
            if not answer:
                region = REGIONS[0]
                break
            # Match the printed labels literally: str.isdigit() also accepts non-ASCII
            # digits, and int() rejects very long digit strings outright.
            if answer in {str(index) for index in range(1, len(REGIONS) + 1)}:
                region = REGIONS[int(answer) - 1]
                break
            print("  Enter a listed number.", file=output)
        allow_writes = ask_yes_no(input_fn, "Allow workflow execution and cancellation? [y/N]: ")
        api_key = ask_key(getpass_fn, output)
        check = ask_yes_no(input_fn, "Verify credentials with Rapid7? [Y/n]: ", default=True)
    except Aborted as error:
        print(f"\n{error}.", file=output)
        return 2

    try:
        settings = Settings(api_key=api_key, region=region, allow_writes=allow_writes)  # type: ignore[arg-type]
    except ValueError:
        print("Invalid credential configuration; nothing was saved.", file=output)
        return 1
    return finish_configuration(settings, check, output, transport)


def finish_configuration(
    settings: Settings,
    check: bool,
    output: IO[str],
    transport: httpx.AsyncBaseTransport | None,
) -> int:
    if check:
        failure = asyncio.run(verify_credentials(settings, transport=transport))
        if failure is not None:
            print(f"\nVerification failed: {failure}", file=output)
            print(
                "Existing credentials were left unchanged; nothing was saved.",
                file=output,
            )
            return 1
        print("\nRapid7 authentication succeeded", file=output)
    else:
        print("Credentials not verified (verification declined).", file=output)
    try:
        persist_settings(settings)
    except (OSError, ValueError):
        print("Could not save credentials securely; check storage permissions.", file=output)
        return 1
    summary = summary_of(settings)
    writes = "enabled" if summary.writes_enabled else "disabled"
    print(f"Credentials saved. Region: {summary.region}", file=output)
    print(f"Writes {writes}", file=output)
    print("\nConfiguration saved for future MCP sessions.", file=output)
    print("Restart any already-running MCP client sessions.", file=output)
    return 0
