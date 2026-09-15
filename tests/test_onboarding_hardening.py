"""Regression tests for onboarding edge cases imported from PR #9 review."""

import io
import json

import pytest
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from pydantic import SecretStr

from insightconnect_mcp.config import ConfigurationSource, Settings, resolve_settings
from insightconnect_mcp.setup_wizard import ask_region, ask_yes_no
from insightconnect_mcp.storage import load_credentials, save_credentials

SECRET = "secret-leak-regression-sentinel"  # noqa: S105 - deliberate test sentinel


@pytest.mark.parametrize(
    "env",
    [
        {"R7_API_KEY": SECRET, "R7_REGION": SECRET},
        {"R7_API_KEY": SECRET, "R7_REGION": "us", "R7_ALLOW_WRITES": SECRET},
        {"R7_API_KEY": f"{SECRET}\n", "R7_REGION": "us"},
    ],
)
def test_invalid_environment_values_are_sanitized(env):
    result = resolve_settings(env)
    assert result.source is ConfigurationSource.ENVIRONMENT
    assert result.settings is None
    assert SECRET not in str(result)

    with pytest.raises(ValueError) as raised:
        Settings.load(env)
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize("answer", ["²", "١", "9" * 5000])
def test_region_prompt_rejects_unusual_numeric_input(answer):
    replies = iter([answer, "4"])
    output = io.StringIO()
    assert ask_region(lambda _: next(replies), output) == "eu"
    assert "Enter a listed number" in output.getvalue()


@pytest.mark.parametrize("default", [False, True])
def test_yes_no_prompt_reprompts_on_unknown_answer(default):
    replies = iter(["maybe", ""])
    assert ask_yes_no(lambda _: next(replies), "Question?", default=default) is default
    assert list(replies) == []


def test_dangling_credential_symlink_fails_closed(tmp_path):
    path = save_credentials(Settings(api_key=SecretStr("stored-key"), region="eu"))
    backup = tmp_path / "credential-backup.json"
    path.rename(backup)
    path.symlink_to(path.with_name("missing.json"))

    with pytest.raises(ValueError, match="regular file"):
        load_credentials()


@pytest.mark.parametrize("writes", [False, True])
async def test_fresh_stdio_process_loads_stored_settings(writes):
    from test_setup_tool import parameters

    settings = Settings(api_key=SecretStr("stored-key"), region="eu", allow_writes=writes)
    path = save_credentials(settings)
    config_home = path.parent.parent

    async with stdio_client(parameters(config_home)) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            resource = await session.read_resource("insightconnect://server/config")

    payload = json.loads(resource.contents[0].text)
    assert payload["configured"] is True
    assert payload["setup_required"] is False
    assert payload["region"] == "eu"
    assert payload["writes_enabled"] is writes
    assert payload["recommended_next_action"] == "list_workflows"
    assert "stored-key" not in resource.model_dump_json()
