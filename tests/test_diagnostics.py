import io

import httpx
import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings, resolve_settings
from insightconnect_mcp.diagnostics import diagnose, run_doctor
from insightconnect_mcp.storage import credentials_path, save_credentials

KEY = "diagnostic-secret-sentinel"


@pytest.mark.parametrize(
    "env",
    [
        {"R7_API_KEY": KEY},
        {"R7_REGION": KEY},
        {"R7_ALLOW_WRITES": KEY},
        {"R7_API_KEY": "", "R7_REGION": "us"},
        {"R7_API_KEY": KEY, "R7_REGION": KEY},
    ],
)
def test_resolution_fail_closed_and_sanitized(env):
    save_credentials(Settings(api_key=SecretStr(KEY), region="eu"))
    result = resolve_settings(env)
    assert result.source == "environment"
    assert result.settings is None
    assert KEY not in str(result)


@pytest.mark.parametrize("stored", [False, True])
async def test_offline_never_contacts_rapid7(stored):
    if stored:
        save_credentials(Settings(api_key=SecretStr(KEY), region="eu"))

    def forbidden(request):
        pytest.fail("offline diagnostics made a network request")

    checks = await diagnose(environ={}, transport=httpx.MockTransport(forbidden))
    assert any(c.name == "connectivity" and "Not checked" in c.message for c in checks)
    assert KEY not in str(checks)
    assert any(c.status == "fail" for c in checks) is not stored


@pytest.mark.parametrize("kind", ["json", "permissions", "directory", "symlink"])
async def test_unsafe_storage_fails(kind):
    path = save_credentials(Settings(api_key=SecretStr(KEY), region="us"))
    if kind == "json":
        path.write_text(KEY)
    elif kind == "permissions":
        path.chmod(0o644)
    elif kind == "directory":
        path.parent.chmod(0o777)
    else:
        other = path.with_suffix(".backup")
        path.rename(other)
        path.symlink_to(other)
    checks = await diagnose(environ={})
    assert any(c.status == "fail" for c in checks)
    assert KEY not in str(checks)


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (200, "succeeded"),
        (401, "401"),
        (403, "403"),
        ("network", "connection failed"),
        ("timeout", "timed out"),
        ("malformed", "JSON object"),
    ],
)
async def test_online_read_only_sanitized(outcome, expected):
    def respond(request):
        assert request.method == "GET"
        assert request.url.path == "/connect/v2/workflows"
        assert request.url.params["limit"] == "1"
        if outcome == "network":
            raise httpx.ConnectError(KEY)
        if outcome == "timeout":
            raise httpx.ReadTimeout(KEY)
        if outcome == "malformed":
            return httpx.Response(200, text=KEY)
        return httpx.Response(outcome, json={"message": KEY})

    checks = await diagnose(
        online=True,
        environ={"R7_API_KEY": KEY, "R7_REGION": "eu"},
        transport=httpx.MockTransport(respond),
    )
    assert expected in checks[-1].message
    assert KEY not in str(checks)


def test_doctor_renders_missing_config():
    output = io.StringIO()
    assert run_doctor(output=output) == 1
    assert "not configured" in output.getvalue()
    assert not credentials_path().exists()
