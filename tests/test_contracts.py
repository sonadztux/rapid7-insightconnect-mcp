"""Offline checks against the vendored official API, not live Rapid7 infrastructure."""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from rapid7_insightconnect_mcp.client import InsightConnectClient
from rapid7_insightconnect_mcp.config import Settings
from rapid7_insightconnect_mcp.server import create_server

ID = "11111111-1111-4111-8111-111111111111"
SPEC = Path(__file__).resolve().parents[1] / "docs" / "insightconnect-api-v1.yaml"


@pytest.mark.parametrize(
    "tool,arguments,path,query",
    [
        (
            "list_workflows",
            {"limit": 5, "offset": 10, "state": "active", "name": "test & name"},
            "/connect/v2/workflows",
            {"limit": "5", "offset": "10", "state": "active", "name": "test & name"},
        ),
        (
            "list_jobs",
            {"limit": 5, "offset": 10, "workflow_id": ID, "status": "failed"},
            "/connect/v1/jobs",
            {"limit": "5", "offset": "10", "workflowId": ID, "status": "failed"},
        ),
        (
            "list_global_artifacts",
            {"limit": 5, "offset": 10, "name": "test", "sort_order": "desc"},
            "/connect/v1/globalArtifacts",
            {
                "limit": "5",
                "offset": "10",
                "filterText": "test",
                "sortBy": "name",
                "sortOrder": "desc",
            },
        ),
    ],
)
async def test_documented_query_mapping(tool, arguments, path, query):
    def respond(request):
        assert request.url.path == path
        assert dict(request.url.params) == query
        return httpx.Response(200, json={"data": {}})

    config = Settings(api_key=SecretStr("test-key"), region="us")
    async with InsightConnectClient(config, transport=httpx.MockTransport(respond)) as client:
        await create_server(config, client=client).call_tool(tool, arguments)


@pytest.mark.parametrize(
    "tool,arguments,payload",
    [
        ("get_workflow", {"workflow_id": ID}, {"data": {"publishedVersion": None}}),
        ("get_job", {"job_id": ID}, {"data": {"job": {"job": {"status": "running"}}}}),
        ("get_global_artifact", {"artifact_id": ID}, {"data": {"globalartifact": {"id": ID}}}),
        ("list_artifact_entries", {"artifact_id": ID}, {"data": {"entities": [{"data": "text"}]}}),
        ("export_snippet", {"snippet_id": ID}, {"name": "snippet", "steps": [], "graph": {}}),
    ],
)
async def test_upstream_shapes_are_preserved(tool, arguments, payload):
    config = Settings(api_key=SecretStr("test-key"), region="us")
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    async with InsightConnectClient(config, transport=transport) as client:
        blocks, structured = await create_server(config, client=client).call_tool(tool, arguments)
        assert structured == payload
        assert json.loads(blocks[0].text) == payload


def test_routes_exist_in_official_snapshot():
    spec = SPEC.read_text()
    for path in [
        "/connect/v2/workflows",
        "/connect/v2/workflows/{workflowId}",
        "/connect/v1/execute/async/workflows/{workflowId}",
        "/connect/v1/jobs",
        "/connect/v1/jobs/{jobId}",
        "/connect/v1/jobs/{jobId}/events/cancel",
        "/connect/v1/globalArtifacts",
        "/connect/v1/globalArtifacts/{globalArtifactId}",
        "/connect/v1/globalArtifacts/{globalArtifactId}/entities",
        "/connect/v2/snippets/{snippetId}/export",
    ]:
        assert f"  {path}:" in spec


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("execute_workflow", {"workflow_id": ID, "confirm": True}),
        ("cancel_job", {"job_id": ID, "confirm": True}),
    ],
)
async def test_mutations_have_no_undocumented_body(tool, arguments):
    def respond(request):
        assert request.content == b""
        return httpx.Response(202, json={})

    config = Settings(api_key=SecretStr("test-key"), region="us", allow_writes=True)
    async with InsightConnectClient(config, transport=httpx.MockTransport(respond)) as client:
        await create_server(config, client=client).call_tool(tool, arguments)
