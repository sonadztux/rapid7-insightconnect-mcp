"""End-to-end onboarding through the MCP session, standing in for an MCP client."""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext

from insightconnect_mcp.server import collect
from insightconnect_mcp.setup_form import OneShotForm
from insightconnect_mcp.storage import credentials_path

KEY = "client-flow-key"
LAUNCHER = str(Path(sys.executable).parent / "rapid7-insightconnect-mcp")


def parameters(config_home, setup_timeout=None):
    env = {key: value for key, value in os.environ.items() if not key.startswith("R7_")}
    env.pop("XDG_CONFIG_HOME", None)
    if setup_timeout is not None:
        env["R7_SETUP_TIMEOUT"] = str(setup_timeout)
    return StdioServerParameters(
        command=LAUNCHER, args=[], env={**env, "XDG_CONFIG_HOME": str(config_home)}
    )


def responder(action="accept", submit=None, seen=None):
    """Stands in for an MCP client that shows the URL and lets the user open it."""

    async def callback(context: RequestContext, params):
        if seen is not None:
            seen.append(params)
        if action == "accept" and submit is not None:
            async with httpx.AsyncClient() as http:
                await http.post(params.url, data=submit, timeout=10)
        return types.ElicitResult(action=action)

    return callback


@pytest.fixture
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


async def test_setup_stops_waiting_when_the_client_never_answers():
    """An unanswered elicitation would otherwise hold the listener and token open."""

    class Silent:
        async def elicit_url(self, **_kwargs):
            await asyncio.sleep(30)

    async with OneShotForm(timeout=0.2) as form:
        message, settings = await asyncio.wait_for(collect(Silent(), form), timeout=5)
    assert settings is None
    assert "timed out" in message


async def run_setup_tool(config_home, callback, setup_timeout=None):
    async with stdio_client(parameters(config_home, setup_timeout)) as (reader, writer):
        async with ClientSession(reader, writer, elicitation_callback=callback) as session:
            await session.initialize()
            result = await session.call_tool("setup", {})
            return result, session


async def test_unconfigured_resource_exposes_onboarding_next_step(config_home):
    async with stdio_client(parameters(config_home)) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            config = await session.read_resource("insightconnect://server/config")

    state = json.loads(config.contents[0].text)
    assert state["configured"] is False
    assert state["setup_required"] is True
    assert state["recommended_next_action"] == "setup"
    assert KEY not in config.model_dump_json()


async def test_client_receives_a_loopback_url_and_not_the_key(config_home):
    seen = []
    result, _ = await run_setup_tool(
        config_home,
        responder(action="decline", seen=seen),
    )
    assert seen[0].mode == "url"
    assert seen[0].url.startswith("http://127.0.0.1:")
    assert "declined" in result.content[0].text
    assert not credentials_path().exists()


async def test_successful_flow_stores_credential_and_activates_tools(config_home, tmp_path):
    """The stored credential activates tools immediately, checked without any
    request leaving the machine: the write guard gets past the configuration
    check and stops only at the missing confirmation."""
    submit = {"region": "eu", "api_key": KEY, "allow_writes": "on"}
    job = {"job_id": "11111111-1111-4111-8111-111111111111"}

    async with stdio_client(parameters(tmp_path / "server")) as (reader, writer):
        async with ClientSession(
            reader, writer, elicitation_callback=responder(submit=submit)
        ) as session:
            await session.initialize()
            before = await session.call_tool("cancel_job", job)
            assert before.isError
            assert "not connected yet" in before.content[0].text
            assert "`uvx rapid7-insightconnect-mcp configure`" in before.content[0].text
            assert "paste an API key" in before.content[0].text

            result = await session.call_tool("setup", {})
            text = result.content[0].text
            assert KEY not in text
            assert "Rapid7 connected successfully" in text
            assert "Region: eu" in text
            assert "Writes: enabled" in text
            assert "list_workflows" in text
            assert "read-only" in text

            config = await session.read_resource("insightconnect://server/config")
            active = json.loads(config.contents[0].text)
            assert active["configured"] is True
            assert active["region"] == "eu"
            assert active["writes_enabled"] is True
            assert active["setup_required"] is False
            assert active["recommended_next_action"] == "list_workflows"
            assert KEY not in config.model_dump_json()

            after = await session.call_tool("cancel_job", job)
            assert after.isError
            assert "Explicit user approval required" in after.content[0].text

    stored = json.loads(
        (tmp_path / "server" / "rapid7-insightconnect-mcp" / "credentials.json").read_text()
    )
    assert stored["region"] == "eu"
    assert stored["allow_writes"] is True
    assert stored["api_key"] == KEY


async def test_timeout_and_bad_submission_store_nothing(config_home, tmp_path):
    """Bad region keeps the form open; the short window then expires cleanly."""
    result, _ = await run_setup_tool(
        tmp_path / "server",
        responder(submit={"region": "mars", "api_key": KEY}),
        setup_timeout=2,
    )
    assert "timed out" in result.content[0].text
    assert not credentials_path().exists()


async def test_client_without_elicitation_gets_copy_paste_uvx_configure_fallback(config_home):
    async with stdio_client(parameters(config_home)) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool("setup", {})

    text = result.content[0].text
    assert "terminal" in text
    assert "`uvx rapid7-insightconnect-mcp configure`" in text
    assert "restart" in text.lower()
    assert "R7_API_KEY" not in text
    assert "secret storage" not in text
    assert "paste" in text.lower()
    assert not credentials_path().exists()


async def test_form_only_client_is_never_sent_the_setup_url(config_home, monkeypatch):
    """URL mode must be declared by the client; the tokenized URL goes nowhere else."""
    monkeypatch.setattr(types, "UrlElicitationCapability", lambda: None)
    seen = []
    result, _ = await run_setup_tool(config_home, responder(seen=seen), setup_timeout=2)
    assert seen == []
    assert "`uvx rapid7-insightconnect-mcp configure`" in result.content[0].text
    assert not credentials_path().exists()


async def test_save_failure_does_not_leak_the_local_filesystem_path(tmp_path):
    """A plain file where the config directory should be makes mkdir() raise
    NotADirectoryError; the tool must not forward that OSError's path to the model."""
    blocker = tmp_path / "occupied"
    blocker.write_text("not a directory")

    result, _ = await run_setup_tool(blocker, responder(submit={"region": "eu", "api_key": KEY}))

    text = result.content[0].text
    assert result.isError
    assert str(blocker) not in text
    assert KEY not in text
    assert "Could not save credentials" in text
