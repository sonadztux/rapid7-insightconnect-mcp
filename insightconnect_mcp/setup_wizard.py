"""Interactive terminal fallback for persistent Rapid7 configuration."""

import asyncio
import getpass as getpass_module
import sys
import warnings
from collections.abc import Callable
from typing import IO, Any, get_args

import httpx
from pydantic import SecretStr

from .config import Region, Settings
from .onboarding import persist_settings, verify_credentials

REGIONS: tuple[str, ...] = get_args(Region)
KEY_ATTEMPTS = 3


class Aborted(Exception):
    """Raised when input is unavailable or the user supplies no credential."""


def ask(input_fn: Callable[[str], str], prompt: str) -> str:
    try:
        return input_fn(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise Aborted("Configuration needs an interactive terminal; run it from a shell") from None


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


def ask_yes_no(input_fn: Callable[[str], str], prompt: str, *, default: bool = False) -> bool:
    answer = ask(input_fn, prompt).lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


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


def run_configure(
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass_module.getpass,
    output: IO[str] = sys.stdout,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: Callable[[Any], Any] = asyncio.run,
) -> int:
    """Configure and persist Rapid7 settings without knowing which harness will use them."""
    print("Rapid7 InsightConnect MCP configuration\n", file=output)
    try:
        region = ask_region(input_fn, output)
        allow_writes = ask_yes_no(input_fn, "Allow workflow execution and cancellation? [y/N]: ")
        key = ask_key(getpass_fn, output)
        check = ask_yes_no(input_fn, "Verify credentials with Rapid7? [Y/n]: ", default=True)
    except Aborted as error:
        print(f"\n{error}.", file=output)
        return 2

    settings = Settings(api_key=key, region=region, allow_writes=allow_writes)  # type: ignore[arg-type]
    if check:
        failure = runner(verify_credentials(settings, transport))
        if failure:
            print(f"\nVerification failed: {failure}", file=output)
            print("Existing stored credentials were not changed.", file=output)
            return 1
        print("\n✓ Rapid7 authentication succeeded", file=output)
    else:
        print("\n○ Rapid7 authentication was not checked", file=output)

    try:
        persist_settings(settings)
    except OSError as error:
        detail = error.strerror or "local credential storage rejected the write"
        print(f"✗ Could not save credentials: {detail}", file=output)
        return 1

    writes = "enabled" if allow_writes else "disabled"
    print("✓ Credentials saved", file=output)
    print(f"✓ Region: {region}", file=output)
    print(f"✓ Writes {writes}", file=output)
    print(
        "\nRestart any already-running MCP client sessions to load the saved settings.", file=output
    )
    return 0


def run_setup(
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass_module.getpass,
    output: IO[str] = sys.stdout,
    transport: httpx.AsyncBaseTransport | None = None,
    runner: Callable[[Any], Any] = asyncio.run,
) -> int:
    """Compatibility wrapper for callers of the old terminal setup entry point."""
    return run_configure(
        input_fn=input_fn,
        getpass_fn=getpass_fn,
        output=output,
        transport=transport,
        runner=runner,
    )
