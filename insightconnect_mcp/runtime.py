"""Holds the active credential so setup can enable tools without a restart."""

from .client import InsightConnectClient
from .config import Settings

UNCONFIGURED = (
    "Rapid7 is not connected yet. Call the `setup` tool before using Rapid7 tools. "
    "Never ask the user to paste an API key into chat. If the client cannot open the setup "
    "page, run `uvx rapid7-insightconnect-mcp configure` in a terminal and restart the MCP "
    "session."
)


class NotConfigured(Exception):
    """Raised when a domain tool runs before credentials exist."""


class Runtime:
    def __init__(
        self, settings: Settings | None = None, client: InsightConnectClient | None = None
    ) -> None:
        self._settings = settings
        self._client = client
        if settings is not None and client is None:
            self._client = InsightConnectClient(settings)

    @property
    def settings(self) -> Settings | None:
        return self._settings

    @property
    def configured(self) -> bool:
        return self._settings is not None and self._client is not None

    def client(self) -> InsightConnectClient:
        if self._settings is None or self._client is None:
            raise NotConfigured(UNCONFIGURED)
        return self._client

    def require_settings(self) -> Settings:
        if self._settings is None:
            raise NotConfigured(UNCONFIGURED)
        return self._settings

    async def configure(self, settings: Settings) -> None:
        previous = self._client
        self._settings = settings
        self._client = InsightConnectClient(settings)
        if previous is not None:
            await previous.__aexit__(None, None, None)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
            self._client = None
