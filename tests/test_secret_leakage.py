"""Sentinel regressions for onboarding surfaces; no live Rapid7 traffic."""

import json

import httpx
import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings, resolve_settings
from insightconnect_mcp.server import create_server
from insightconnect_mcp.storage import load_credentials, save_credentials

SECRET = "secret-leak-regression-sentinel"  # noqa: S105 — deliberate test sentinel


@pytest.mark.parametrize("field", ["R7_REGION", "R7_ALLOW_WRITES", "R7_API_KEY"])
def test_environment_errors_never_echo_values(field):
    env = {"R7_API_KEY": SECRET, "R7_REGION": "eu"}
    env[field] = SECRET + " invalid"
    with pytest.raises(ValueError) as raised:
        Settings.from_env(env)
    assert SECRET not in str(raised.value)
    assert SECRET not in str(resolve_settings(env))


@pytest.mark.parametrize("configured", [False, True])
async def test_config_resource_and_instructions_are_safe(configured):
    settings = Settings(api_key=SecretStr(SECRET), region="eu") if configured else None
    server = create_server(settings)
    result = await server.read_resource("insightconnect://server/config")
    text = list(result)[0].content
    payload = json.loads(text)
    assert payload["setup_required"] is not configured
    assert payload["recommended_next_action"] == ("list_workflows" if configured else "setup")
    assert SECRET not in text + server.instructions


async def test_setup_activates_read_only_tools_without_restart(monkeypatch, caplog):
    from insightconnect_mcp import server as module
    from insightconnect_mcp.client import InsightConnectClient

    settings = Settings(api_key=SecretStr(SECRET), region="eu")

    async def collect(*args):
        return None, settings

    monkeypatch.setattr(module, "collect", collect)
    monkeypatch.setattr(module, "supports_url_elicitation", lambda _: True)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"message": SECRET})

    monkeypatch.setattr(
        "insightconnect_mcp.runtime.InsightConnectClient",
        lambda config: InsightConnectClient(config, transport=httpx.MockTransport(respond)),
    )
    server = create_server()
    setup = await server.call_tool("setup", {})
    result = await server.call_tool("list_workflows", {"limit": 1})
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert SECRET not in str(setup) + str(result) + caplog.text
    assert load_credentials() == settings
    assert Settings.load({}) == settings


def test_invalid_stored_values_are_sanitized():
    path = save_credentials(Settings(api_key=SecretStr(SECRET), region="us"))
    path.write_text(json.dumps({"api_key": SECRET, "region": SECRET, "allow_writes": False}))
    with pytest.raises(ValueError) as raised:
        Settings.load({})
    assert SECRET not in str(raised.value)
