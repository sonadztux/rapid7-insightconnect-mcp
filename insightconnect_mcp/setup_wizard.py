"""Interactive terminal configuration: the CLI fallback for the MCP setup tool.

Delegates to shared onboarding and secure local storage. The key is never
printed, logged, or turned into harness-specific configuration.
"""

import getpass as getpass_module
import sys
from collections.abc import Callable
from typing import IO, Any

import httpx

from .onboarding import REGIONS, configure_interactively

__all__ = ["REGIONS", "run_configure", "run_setup"]


def run_configure(
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass_module.getpass,
    output: IO[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Interactive configure command; returns a process exit code."""
    if output is None:
        output = sys.stdout
    return configure_interactively(
        input_fn=input_fn,
        getpass_fn=getpass_fn,
        output=output,
        transport=transport,
    )


def run_setup(**kwargs: Any) -> int:
    """Compatibility alias for run_configure."""
    return run_configure(**kwargs)
