"""Command-line entry point for MCP serving, configuration, and diagnostics."""

import sys
from importlib.metadata import version

from .config import Settings
from .diagnostics import run_doctor
from .server import create_server
from .setup_wizard import run_configure

USAGE = """Rapid7 InsightConnect MCP

Usage:
  rapid7-insightconnect-mcp
      Run the MCP server over stdio when launched by an MCP client.

  rapid7-insightconnect-mcp configure
      Configure Rapid7 credentials outside an MCP client.

  rapid7-insightconnect-mcp doctor
      Check local configuration without contacting Rapid7.

  rapid7-insightconnect-mcp doctor --online
      Also perform one read-only Rapid7 API check.

  rapid7-insightconnect-mcp --version
      Show the installed package version.

  rapid7-insightconnect-mcp --help
      Show this message.

Normally you do not run the MCP server directly. Add it through your MCP client's own MCP
command or settings, then use the MCP `setup` tool to connect Rapid7.
"""

INTERACTIVE_GUIDANCE = """Rapid7 InsightConnect MCP is a stdio MCP server.

The bare command is meant to be launched by an MCP-compatible AI client, not used as an
interactive terminal session.

Add this server command to your MCP client:
  uvx rapid7-insightconnect-mcp

Verify the installed package:
  uvx rapid7-insightconnect-mcp --version

Configure Rapid7 from the terminal if needed:
  uvx rapid7-insightconnect-mcp configure

Show all commands:
  uvx rapid7-insightconnect-mcp --help
"""


def serve() -> None:
    """Start even without credentials so the setup tool stays reachable from the client."""
    try:
        settings: Settings | None = Settings.load()
    except ValueError as error:
        print(f"Starting unconfigured: {error}", file=sys.stderr)
        settings = None
    create_server(settings).run(transport="stdio")


def _invalid(command: str) -> None:
    print(f"Unknown or invalid arguments: {command}\n\n{USAGE}", file=sys.stderr)
    raise SystemExit(2)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        if sys.stdin.isatty():
            print(INTERACTIVE_GUIDANCE)
            return
        serve()
        return

    if args in [["help"], ["--help"], ["-h"]]:
        print(USAGE)
        return

    if args == ["--version"]:
        print(version("rapid7-insightconnect-mcp"))
        return

    if args == ["configure"]:
        raise SystemExit(run_configure())

    if args == ["setup"]:
        print("`setup` has been renamed to `configure`. Running configuration...", file=sys.stderr)
        raise SystemExit(run_configure())

    if args == ["doctor"]:
        raise SystemExit(run_doctor())

    if args == ["doctor", "--online"]:
        raise SystemExit(run_doctor(online=True))

    _invalid(" ".join(args))