"""Shared Rapid7 onboarding helpers used by MCP setup and CLI configuration."""

from pathlib import Path

import httpx

from .client import ApiError, InsightConnectClient
from .config import Settings
from .storage import save_credentials


async def verify_credentials(
    settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> str | None:
    """Verify credentials with one read-only workflow request.

    Returns a sanitized error message on failure, otherwise ``None``.
    """
    async with InsightConnectClient(settings, transport=transport) as client:
        try:
            await client.request("GET", "connect/v2/workflows", params={"limit": 1})
        except ApiError as error:
            return str(error)
    return None


def persist_settings(settings: Settings) -> Path:
    """Persist settings using the hardened owner-only credential store."""
    return save_credentials(settings)
