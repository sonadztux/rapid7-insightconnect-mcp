import asyncio
import gzip
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from insightconnect_mcp.client import ApiError, InsightConnectClient
from insightconnect_mcp.config import Settings


@pytest.fixture
def settings():
    return Settings(api_key=SecretStr("test-secret"), region="us")


def test_config_reads_environment_without_exposing_key():
    config = Settings.from_env({"R7_API_KEY": "test-secret", "R7_REGION": "eu"})
    assert config.base_url == "https://eu.api.insight.rapid7.com/"
    assert "test-secret" not in repr(config)
    assert config.allow_writes is False


@pytest.mark.parametrize("region", ["", "https://evil.invalid", "../us", "us.evil.invalid"])
def test_config_rejects_untrusted_hosts(region):
    with pytest.raises(ValidationError):
        Settings(api_key=SecretStr("key"), region=region)


@pytest.mark.parametrize("key", ["", " ", "key\nheader", "key\rheader"])
def test_config_rejects_invalid_credentials(key):
    with pytest.raises(ValidationError):
        Settings(api_key=SecretStr(key), region="us")


def test_config_requires_credentials_and_region():
    with pytest.raises(ValueError, match="R7_API_KEY and R7_REGION"):
        Settings.from_env({})
    with pytest.raises(ValueError, match="R7_ALLOW_WRITES"):
        Settings.from_env({"R7_API_KEY": "key", "R7_REGION": "us", "R7_ALLOW_WRITES": "yes"})


async def test_request_auth_url_query_and_json(settings):
    def respond(request):
        assert str(request.url) == "https://us.api.insight.rapid7.com/connect/v2/workflows?offset=2"
        assert request.headers["X-Api-Key"] == "test-secret"
        return httpx.Response(200, json={"workflows": []})

    async with InsightConnectClient(settings, transport=httpx.MockTransport(respond)) as client:
        assert await client.request("GET", "connect/v2/workflows", params={"offset": 2}) == {
            "workflows": []
        }


@pytest.mark.parametrize(
    "path", ["https://evil.invalid", "//evil.invalid", "../jobs", "/jobs", "jobs?x=1"]
)
async def test_request_rejects_untrusted_paths(settings, path):
    def no_request(request):
        pytest.fail("invalid path reached HTTP transport")

    async with InsightConnectClient(settings, transport=httpx.MockTransport(no_request)) as client:
        with pytest.raises(ApiError, match="Invalid API path"):
            await client.request("GET", path)


@pytest.mark.parametrize("status", [301, 401, 403, 404, 429, 500])
async def test_api_errors_hide_body_and_do_not_retry(settings, status):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="test-secret sensitive upstream details",
            headers={"Location": "https://evil.invalid"},
        )

    async with InsightConnectClient(settings, transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ApiError) as error:
            await client.request("GET", "jobs")
    assert str(status) in str(error.value)
    assert "test-secret" not in str(error.value)
    assert "sensitive" not in str(error.value)
    assert len(calls) == 1


async def test_timeout_is_sanitized(settings):
    def respond(request):
        raise httpx.ReadTimeout("test-secret", request=request)

    async with InsightConnectClient(settings, transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ApiError, match="timed out") as error:
            await client.request("POST", "jobs", body={})
    assert "test-secret" not in str(error.value)


@pytest.mark.parametrize("content", [b"not json", b"[]", b"null"])
async def test_bad_response_is_sanitized(settings, content):
    async with InsightConnectClient(
        settings, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content))
    ) as client:
        with pytest.raises(ApiError, match="JSON object"):
            await client.request("GET", "jobs")


async def test_response_and_payload_limits(settings):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * 101))
    async with InsightConnectClient(settings, transport=transport, max_bytes=100) as client:
        with pytest.raises(ApiError, match="Response exceeds"):
            await client.request("GET", "jobs")
        with pytest.raises(ApiError, match="Request exceeds"):
            await client.request("POST", "jobs", body={"data": "x" * 101})


async def test_empty_success_and_secret_redaction(settings):
    responses = iter([httpx.Response(204), httpx.Response(200, json={"echo": "test-secret"})])
    async with InsightConnectClient(
        settings, transport=httpx.MockTransport(lambda _: next(responses))
    ) as client:
        assert await client.request("DELETE", "jobs/id") == {}
        assert "test-secret" not in json.dumps(await client.request("GET", "jobs"))


@pytest.mark.parametrize("key", ['test"key', "test\\key"])
async def test_escaped_credentials_are_redacted(key):
    config = Settings(api_key=SecretStr(key), region="us")
    payload = {key: [key, {"nested": "prefix" + key + "suffix"}]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    async with InsightConnectClient(config, transport=transport) as client:
        result = await client.request("GET", "jobs")
    assert result == {"[REDACTED]": ["[REDACTED]", {"nested": "prefix[REDACTED]suffix"}]}


async def test_compressed_response_is_rejected(settings):
    def respond(request):
        assert request.headers["Accept-Encoding"] == "identity"
        return httpx.Response(
            200, content=gzip.compress(b"x" * 1000), headers={"Content-Encoding": "gzip"}
        )

    async with InsightConnectClient(settings, transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ApiError, match="compression"):
            await client.request("GET", "jobs")


async def test_overall_deadline_closes_slow_stream(settings):
    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"{"
            await asyncio.sleep(1)
            yield b"}"

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))
    async with InsightConnectClient(settings, transport=transport, total_timeout=0.01) as client:
        with pytest.raises(ApiError, match="timed out"):
            await client.request("GET", "jobs")
    assert stream.closed


async def test_credential_fields_in_upstream_data_are_redacted(settings):
    """Rapid7 content can carry other people's secrets; the agent must not receive them."""
    body = {
        "data": [{"password": "hunter2", "apiKey": "another-key", "name": "keep-me"}],
        "headers": {"Authorization": "Bearer another-token"},
        "step": {"connection": {"client_secret": "shhh", "private_key": "----BEGIN----"}},
        "page": {"index": 0, "size": 10, "nextPageToken": "cursor-1"},
    }
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=body))
    async with InsightConnectClient(settings, transport=transport) as client:
        result = await client.request("GET", "jobs")
    text = json.dumps(result)
    for secret in ("hunter2", "another-key", "another-token", "shhh", "BEGIN"):
        assert secret not in text
    assert result["data"][0]["name"] == "keep-me"
    # Paging must keep working; only credential-shaped field names are masked.
    assert result["page"] == {"index": 0, "size": 10, "nextPageToken": "cursor-1"}
