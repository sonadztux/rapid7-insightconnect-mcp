import os
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_point", [False, True])
async def test_standard_stdio_discovery_and_resources(entry_point):
    parameters = StdioServerParameters(
        command=(
            str(Path(sys.executable).parent / "rapid7-insightconnect-mcp")
            if entry_point
            else sys.executable
        ),
        args=[] if entry_point else ["-m", "rapid7_insightconnect_mcp"],
        env={
            **os.environ,
            "R7_API_KEY": "stdio-fake-key",
            "R7_REGION": "us",
            "R7_ALLOW_WRITES": "false",
        },
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "rapid7-insightconnect"
            assert initialized.serverInfo.version == version("rapid7-insightconnect-mcp")
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            assert {
                "list_workflows",
                "get_workflow",
                "execute_workflow",
                "list_jobs",
                "get_job",
                "cancel_job",
                "list_global_artifacts",
                "get_global_artifact",
                "list_artifact_entries",
                "export_snippet",
            } <= tools.keys()
            assert tools["execute_workflow"].annotations.destructiveHint is True
            assert tools["list_workflows"].annotations.readOnlyHint is True
            assert tools["get_job"].inputSchema["properties"]["job_id"]["format"] == "uuid"
            resources = await session.list_resources()
            assert "insightconnect://server/config" in {
                str(item.uri) for item in resources.resources
            }
            config = await session.read_resource("insightconnect://server/config")
            assert "stdio-fake-key" not in config.model_dump_json()
            assert '"writes_enabled": false' in config.contents[0].text
            result = await session.call_tool("get_job", {"job_id": "not-a-uuid"})
            assert result.isError
            denied = await session.call_tool(
                "cancel_job",
                {
                    "job_id": "11111111-1111-4111-8111-111111111111",
                    "confirm": True,
                },
            )
            assert denied.isError
            assert "R7_ALLOW_WRITES" in denied.content[0].text
