"""Interactive onboarding. The key is held only in memory and never printed or stored."""

import asyncio
import getpass as getpass_module
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any, get_args

import httpx
from pydantic import SecretStr

from .client import ApiError, InsightConnectClient
from .config import Region, Settings

REGIONS: tuple[str, ...] = get_args(Region)
KEY_ATTEMPTS = 3
PLACEHOLDER = "PASTE_YOUR_KEY_HERE"


class Aborted(Exception):
    """Raised when input is unavailable or the user supplies no credential."""


def ask(input_fn: Callable[[str], str], prompt: str) -> str:
    try:
        return input_fn(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise Aborted("Setup needs an interactive terminal; run it from a shell") from None


def ask_region(input_fn: Callable[[str], str], output: IO[str]) -> str:
    for index, region in enumerate(REGIONS, start=1):
        print(f"  {index}) {region}", file=output)
    while True:
        answer = ask(input_fn, "Region number [1]: ")
        if not answer:
            return REGIONS[0]
        if answer.isdigit() and 1 <= int(answer) <= len(REGIONS):
            return REGIONS[int(answer) - 1]
        print("  Enter a listed number.", file=output)


def ask_yes_no(input_fn: Callable[[str], str], prompt: str) -> bool:
    return ask(input_fn, prompt).lower() in {"y", "yes"}


def ask_key(getpass_fn: Callable[[str], str], output: IO[str]) -> SecretStr:
    for _ in range(KEY_ATTEMPTS):
        try:
            key = getpass_fn("API key (input hidden): ").strip()
        except (EOFError, KeyboardInterrupt):
            raise Aborted("Setup needs an interactive terminal; run it from a shell") from None
        if key:
            return SecretStr(key)
        print("  Empty input.", file=output)
    raise Aborted("Setup received no API key")


async def verify(settings: Settings, transport: httpx.AsyncBaseTransport | None) -> str | None:
    """Read-only probe using the user's own credential. Returns an error message or None."""
    async with InsightConnectClient(settings, transport=transport) as client:
        try:
            await client.request("GET", "connect/v2/workflows", params={"limit": 1})
        except ApiError as error:
            return str(error)
    return None


def launcher() -> str:
    """Harness configuration needs an absolute path, not the invoking argv[0]."""
    installed = Path(sys.executable).parent / "rapid7-insightconnect-mcp"
    return str(installed if installed.exists() else Path(sys.argv[0]).resolve())


def render(region: str, allow_writes: bool, output: IO[str]) -> None:
    snippet = {
        "mcpServers": {
            "rapid7-insightconnect": {
                "command": launcher(),
                "args": [],
                "env": {
                    "R7_API_KEY": PLACEHOLDER,
                    "R7_REGION": region,
                    "R7_ALLOW_WRITES": "true" if allow_writes else "false",
                },
            }
        }
    }
    print("\nAdd this local/stdio server to your harness:\n", file=output)
    print(json.dumps(snippet, indent=2), file=output)
    print(
        f"\nReplace {PLACEHOLDER} using your harness's secret mechanism."
        "\nThe key you typed was discarded and never written to disk.",
        file=output,
    )


def run_setup(
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass_module.getpass,
    output: IO[str] = sys.stdout,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: Callable[[Any], Any] = asyncio.run,
) -> int:
    print("Rapid7 InsightConnect MCP setup\n", file=output)
    try:
        region = ask_region(input_fn, output)
        allow_writes = ask_yes_no(input_fn, "Allow execute and cancel tools? [y/N]: ")
        key = ask_key(getpass_fn, output)
        check = ask_yes_no(input_fn, "Verify this key against Rapid7 now? [y/N]: ")
    except Aborted as error:
        print(f"\n{error}.", file=output)
        return 2

    settings = Settings(api_key=key, region=region, allow_writes=allow_writes)  # type: ignore[arg-type]
    if check:
        failure = runner(verify(settings, transport))
        if failure:
            print(f"\nVerification failed: {failure}", file=output)
            return 1
        print("\nCredential verified against Rapid7.", file=output)
    else:
        print("\nCredential not verified; no request was made.", file=output)
    render(region, allow_writes, output)
    return 0
