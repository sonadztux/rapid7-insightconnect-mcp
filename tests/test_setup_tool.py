"""End-to-end onboarding through the MCP session, standing in for an MCP client."""

import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext

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


async def run_setup_tool(config_home, callback, setup_timeout=None):
    async with stdio_client(parameters(config_home, setup_timeout)) as (reader, writer):
        async with ClientSession(reader, writer, elicitation_callback=callback) as session:
            await session.initialize()
            result = await session.call_tool("setup", {})
            return result, session


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
            assert "not configured" in before.content[0].text

            result = await session.call_tool("setup", {})
            text = result.content[0].text
            assert KEY not in text
            assert "Ready" in text

            config = await session.read_resource("insightconnect://server/config")
            active = json.loads(config.contents[0].text)
            assert active["configured"] is True
            assert active["region"] == "eu"
            assert active["writes_enabled"] is True
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


async def test_client_without_elicitation_gets_terminal_instructions(config_home):
    async with stdio_client(parameters(config_home)) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool("setup", {})
    assert "terminal" in result.content[0].text
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
