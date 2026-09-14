"""Command-line entry point: serve MCP over stdio, or run the terminal setup wizard."""

import sys

from .config import Settings
from .server import create_server
from .setup_wizard import run_setup

USAGE = (
    "Usage:\n"
    "  rapid7-insightconnect-mcp          Serve MCP over stdio (stored or R7_* credentials)\n"
    "  rapid7-insightconnect-mcp setup    Interactive onboarding wizard\n"
    "  rapid7-insightconnect-mcp --help   Show this message"
)


def serve() -> None:
    """Start even without credentials so the setup tool stays reachable from the client."""
    try:
        settings: Settings | None = Settings.load()
    except ValueError as error:
        print(f"Starting unconfigured: {error}", file=sys.stderr)
        settings = None
    create_server(settings).run(transport="stdio")


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if not command:
        serve()
    elif command == "setup":
        raise SystemExit(run_setup())
    elif command in {"help", "--help", "-h"}:
        print(USAGE)
    else:
        print(f"Unknown argument: {command}\n{USAGE}", file=sys.stderr)
        raise SystemExit(2)
