"""End-to-end onboarding through the MCP session, standing in for a harness client."""

import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from mcp.shared.context import RequestContext

from rapid7_insightconnect_mcp.storage import credentials_path

KEY = "harness-flow-key"
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
    """Stands in for a harness that shows the URL and lets the user open it."""

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
    """The stored credential activates tools immediately. list_workflows reaching
    the real Rapid7 host with a fake key must fail with sanitized 401, proving the
    request went out; a DNS/proxy failure would read differently."""
    submit = {"region": "eu", "api_key": KEY, "allow_writes": "on"}

    async with stdio_client(parameters(tmp_path / "server")) as (reader, writer):
        async with ClientSession(
            reader, writer, elicitation_callback=responder(submit=submit)
        ) as session:
            await session.initialize()
            before = await session.call_tool("list_workflows", {})
            assert before.isError
            assert "not configured" in before.content[0].text

            result = await session.call_tool("setup", {})
            text = result.content[0].text
            assert KEY not in text
            assert "Ready" in text

            after = await session.call_tool("list_workflows", {})
            assert after.isError
            assert "HTTP 401" in after.content[0].text

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
