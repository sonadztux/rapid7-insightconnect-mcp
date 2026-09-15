"""Local onboarding acceptance and regression checks; no live API."""

import io
import json

import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
from insightconnect_mcp.diagnostics import diagnose
from insightconnect_mcp.onboarding import ask_yes_no, configure_interactively
from insightconnect_mcp.storage import load_credentials, save_credentials


@pytest.mark.parametrize("answer", ["²", "9" * 5000, "١"])
def test_unusual_region_reprompts(answer):
    replies = iter([answer, "4", "n", "n"])
    output = io.StringIO()
    assert (
        configure_interactively(
            input_fn=lambda _: next(replies), getpass_fn=lambda _: "fake-gap-key", output=output
        )
        == 0
    )
    assert load_credentials().region == "eu"
    assert "Enter a listed number" in output.getvalue()


@pytest.mark.parametrize("default", [False, True])
def test_unknown_yes_no_reprompts_before_default(default):
    replies = iter(["maybe", ""])
    assert ask_yes_no(lambda _: next(replies), "Question?", default=default) is default
    assert list(replies) == []


async def test_online_invalid_config_never_verifies(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached verifier")

    monkeypatch.setattr("insightconnect_mcp.diagnostics.verify_credentials", forbidden)
    checks = await diagnose(online=True, environ={"R7_API_KEY": "fake", "R7_REGION": "invalid"})
    assert any(check.name == "configuration" and check.status == "fail" for check in checks)
    assert checks[-1].message == "Not checked."


async def test_dangling_credential_symlink_fails_closed():
    path = save_credentials(Settings(api_key=SecretStr("fake-gap-key"), region="eu"))
    path.rename(path.with_suffix(".backup"))
    path.symlink_to(path.with_name("missing.json"))
    with pytest.raises(ValueError, match="permissions"):
        load_credentials()
    checks = await diagnose(environ={})
    assert any(check.name == "storage" and check.status == "fail" for check in checks)


@pytest.mark.parametrize("writes", [False, True])
async def test_fresh_process_loads_stored_settings(tmp_path, writes):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    from test_setup_tool import parameters

    settings = Settings(api_key=SecretStr("fake-gap-key"), region="eu", allow_writes=writes)
    path = save_credentials(settings)
    for _ in range(2):
        async with stdio_client(parameters(path.parent.parent)) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                resource = await session.read_resource("insightconnect://server/config")
                payload = json.loads(resource.contents[0].text)
                assert payload["configured"] is True
                assert payload["setup_required"] is False
                assert payload["region"] == "eu"
                assert payload["writes_enabled"] is writes
                assert payload["recommended_next_action"] == "list_workflows"
                assert "fake-gap-key" not in resource.model_dump_json()
