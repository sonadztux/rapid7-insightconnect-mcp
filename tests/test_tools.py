import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import SecretStr

from insightconnect_mcp.client import InsightConnectClient
from insightconnect_mcp.config import Settings
from insightconnect_mcp.server import create_server

ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    ("tool", "arguments", "method", "path"),
    [
        ("list_workflows", {}, "GET", "/connect/v2/workflows"),
        ("get_workflow", {"workflow_id": ID}, "GET", f"/connect/v2/workflows/{ID}"),
        ("list_jobs", {}, "GET", "/connect/v1/jobs"),
        ("get_job", {"job_id": ID}, "GET", f"/connect/v1/jobs/{ID}"),
        ("list_global_artifacts", {}, "GET", "/connect/v1/globalArtifacts"),
        ("get_global_artifact", {"artifact_id": ID}, "GET", f"/connect/v1/globalArtifacts/{ID}"),
        (
            "list_artifact_entries",
            {"artifact_id": ID},
            "GET",
            f"/connect/v1/globalArtifacts/{ID}/entities",
        ),
        ("export_snippet", {"snippet_id": ID}, "GET", f"/connect/v2/snippets/{ID}/export"),
        (
            "cancel_job",
            {"job_id": ID, "confirm": True},
            "POST",
            f"/connect/v1/jobs/{ID}/events/cancel",
        ),
        (
            "execute_workflow",
            {"workflow_id": ID, "confirm": True},
            "POST",
            f"/connect/v1/execute/async/workflows/{ID}",
        ),
    ],
)
async def test_domain_tool_routes(tool, arguments, method, path):
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == method
        assert request.url.path == path
        return httpx.Response(200, json={"fixture": "ok"})

    config = Settings(api_key=SecretStr("test-key"), region="us", allow_writes=True)
    async with InsightConnectClient(config, transport=httpx.MockTransport(respond)) as client:
        server = create_server(config, client=client)
        result = await server.call_tool(tool, arguments)
        assert "ok" in str(result)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("execute_workflow", {"workflow_id": ID}),
        ("cancel_job", {"job_id": ID}),
    ],
)
@pytest.mark.parametrize("allow_writes,confirm", [(False, False), (False, True), (True, False)])
async def test_write_requires_local_opt_in_and_confirmation(tool, arguments, allow_writes, confirm):
    def no_request(request):
        pytest.fail("denied mutation reached HTTP transport")

    config = Settings(api_key=SecretStr("test-key"), region="us", allow_writes=allow_writes)
    async with InsightConnectClient(config, transport=httpx.MockTransport(no_request)) as client:
        with pytest.raises(ToolError, match="R7_ALLOW_WRITES|confirm"):
            await create_server(config, client=client).call_tool(
                tool, {**arguments, "confirm": confirm}
            )


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("get_workflow", {"workflow_id": "../jobs"}),
        ("get_job", {"job_id": "https://evil.invalid"}),
        ("list_jobs", {"offset": -1}),
        ("list_jobs", {"limit": 31}),
        ("list_workflows", {"offset": -1}),
        ("list_workflows", {"limit": 0}),
        ("cancel_job", {"job_id": ID, "confirm": "true"}),
    ],
)
async def test_invalid_arguments_never_reach_network(tool, arguments):
    def no_request(request):
        pytest.fail("invalid arguments reached HTTP transport")

    config = Settings(api_key=SecretStr("test-key"), region="us", allow_writes=True)
    async with InsightConnectClient(config, transport=httpx.MockTransport(no_request)) as client:
        with pytest.raises(ToolError):
            await create_server(config, client=client).call_tool(tool, arguments)


async def test_tool_api_error_is_safe():
    config = Settings(api_key=SecretStr("test-key"), region="us")
    transport = httpx.MockTransport(lambda _: httpx.Response(401, text="test-key private"))
    async with InsightConnectClient(config, transport=transport) as client:
        with pytest.raises(ToolError) as error:
            await create_server(config, client=client).call_tool("list_jobs", {})
    assert "401" in str(error.value)
    assert "test-key" not in str(error.value)
    assert "private" not in str(error.value)


async def test_export_query_is_explicit():
    def respond(request):
        assert request.url.params["unpublishedVersion"] == "true"
        return httpx.Response(200, json={"snippet": {}})

    config = Settings(api_key=SecretStr("test-key"), region="us")
    async with InsightConnectClient(config, transport=httpx.MockTransport(respond)) as client:
        await create_server(config, client=client).call_tool(
            "export_snippet", {"snippet_id": ID, "unpublished_version": True}
        )


async def test_resource_templates_expose_read_only_detail():
    config = Settings(api_key=SecretStr("test-key"), region="us")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"job": {"id": ID}}))
    async with InsightConnectClient(config, transport=transport) as client:
        server = create_server(config, client=client)
        templates = await server.list_resource_templates()
        assert "insightconnect://jobs/{job_id}" in {item.uriTemplate for item in templates}
        resources = await server.read_resource(f"insightconnect://jobs/{ID}")
        assert json.loads(list(resources)[0].content)["job"]["id"] == ID
