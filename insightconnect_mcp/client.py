"""Bounded HTTP access to the configured Rapid7 regional API."""

import asyncio
import json
import re
from types import TracebackType
from typing import Any, Self

import httpx

from .config import Settings

MAX_BYTES = 2 * 1024 * 1024
REDACTED = "[REDACTED]"
# Rapid7 content (workflow steps, connections, job output) can carry credentials that are
# not this server's own key. Mask credential-shaped field names so they never reach the
# model; paging fields such as nextPageToken stay readable.
CREDENTIAL_FIELD = re.compile(
    r"password|passwd|secret|credential|authorization|bearer"
    r"|(?:api|access|refresh|auth|session)[ _-]?token"
    r"|(?:api|private|public|access|encryption)[ _-]?key",
    re.IGNORECASE,
)


def _is_credential(key: Any) -> bool:
    return isinstance(key, str) and CREDENTIAL_FIELD.search(key) is not None


class ApiError(Exception):
    """Safe error suitable for returning to an MCP client."""


class InsightConnectClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_bytes: int = MAX_BYTES,
        total_timeout: float = 60,
    ) -> None:
        self.settings = settings
        self.max_bytes = max_bytes
        self.total_timeout = total_timeout
        self._http = httpx.AsyncClient(
            base_url=settings.base_url,
            headers={
                "X-Api-Key": settings.api_key.get_secret_value(),
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | bool] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", path):
            raise ApiError("Invalid API path")
        content = self._encode(body)
        try:
            async with (
                asyncio.timeout(self.total_timeout),
                self._http.stream(
                    method,
                    path,
                    params=params,
                    content=content,
                    headers={"Content-Type": "application/json"} if body is not None else {},
                ) as response,
            ):
                if not 200 <= response.status_code < 300:
                    raise ApiError(
                        f"Rapid7 API returned HTTP {response.status_code}; no retry made"
                    )
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise ApiError("Unexpected response compression; response rejected")
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(data) + len(chunk) > self.max_bytes:
                        raise ApiError("Response exceeds size limit; narrow the query or page size")
                    data.extend(chunk)
                return self._decode(bytes(data))
        except (httpx.TimeoutException, TimeoutError):
            raise ApiError(
                "Rapid7 request timed out; outcome may be unknown. No retry made"
            ) from None
        except httpx.HTTPError:
            raise ApiError(
                "Rapid7 connection failed; outcome may be unknown. No retry made"
            ) from None

    def _encode(self, body: dict[str, Any] | None) -> bytes | None:
        if body is None:
            return None
        try:
            content = json.dumps(body, allow_nan=False).encode()
        except (ValueError, TypeError, RecursionError):
            raise ApiError("Request must contain valid JSON") from None
        if len(content) > self.max_bytes:
            raise ApiError("Request exceeds size limit")
        return content

    def _decode(self, content: bytes) -> dict[str, Any]:
        if not content:
            return {}
        try:
            result = json.loads(content)
        except (ValueError, RecursionError):
            raise ApiError("Rapid7 response must be a JSON object") from None
        if not isinstance(result, dict):
            raise ApiError("Rapid7 response must be a JSON object")
        try:
            return dict(self._redact(result))
        except RecursionError:
            raise ApiError("Rapid7 JSON response nesting exceeds limit") from None

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(self.settings.api_key.get_secret_value(), REDACTED)
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, dict):
            return {
                self._redact(key): REDACTED if _is_credential(key) else self._redact(item)
                for key, item in value.items()
            }
        return value
