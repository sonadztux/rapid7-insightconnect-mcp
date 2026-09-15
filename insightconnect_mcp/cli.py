"""Command-line entry point: serve MCP over stdio by default; configure and doctor as commands.

The harness owns MCP registration; this CLI only configures and diagnoses this server's
own Rapid7 setup. It never generates harness-specific configuration.
"""

import sys
from importlib.metadata import version as package_version

from .server import create_server

USAGE = """\
Rapid7 InsightConnect MCP

Usage:
  rapid7-insightconnect-mcp
      Run the MCP server over stdio.

  rapid7-insightconnect-mcp configure
      Configure Rapid7 credentials outside an MCP client.

  rapid7-insightconnect-mcp doctor
      Check local configuration and credential storage.

  rapid7-insightconnect-mcp doctor --online
      Also perform a read-only Rapid7 API check.

  rapid7-insightconnect-mcp --version
      Show version.

Normally you do not run the MCP server directly.
Add it through your MCP client's own MCP command or settings."""


def serve() -> None:
    """Start even without credentials so the setup tool stays reachable from the client."""
    from .config import resolve_settings

    resolution = resolve_settings()
    if resolution.settings is None and resolution.error:
        print(f"Starting unconfigured: {resolution.error}", file=sys.stderr)
    create_server(resolution.settings).run(transport="stdio")


def main() -> None:
    args = sys.argv[1:]
    if len(args) > 1 and args != ["doctor", "--online"]:
        print(f"Invalid arguments.\n\n{USAGE}", file=sys.stderr)
        raise SystemExit(2)
    command = args[0] if args else ""
    if not command:
        serve()
    elif command == "configure":
        from .setup_wizard import run_configure

        raise SystemExit(run_configure())
    elif command == "setup":
        print("`setup` has been renamed to `configure`.\nRunning configuration...")
        from .setup_wizard import run_configure

        raise SystemExit(run_configure())
    elif command == "doctor":
        from .diagnostics import run_doctor

        raise SystemExit(run_doctor(online="--online" in sys.argv[2:]))
    elif command in {"--version", "-V", "version"}:
        print(package_version("rapid7-insightconnect-mcp"))
    elif command in {"help", "--help", "-h"}:
        print(USAGE)
    else:
        print(f"Unknown argument.\n\n{USAGE}", file=sys.stderr)
        raise SystemExit(2)
