import io

import httpx
import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
from insightconnect_mcp.diagnostics import run_doctor
from insightconnect_mcp.storage import save_credentials

KEY = "doctor-secret-key"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for name in ("R7_API_KEY", "R7_REGION", "R7_ALLOW_WRITES"):
        monkeypatch.delenv(name, raising=False)


def test_local_doctor_reports_unconfigured_without_network():
    output = io.StringIO()
    assert run_doctor(output=output) == 1
    text = output.getvalue()
    assert "configuration required" in text
    assert KEY not in text


def test_local_doctor_reports_region_and_write_policy():
    save_credentials(Settings(api_key=SecretStr(KEY), region="eu", allow_writes=False))
    output = io.StringIO()
    assert run_doctor(output=output) == 0
    text = output.getvalue()
    assert "Region: eu" in text
    assert "Writes disabled" in text
    assert "Not checked" in text
    assert KEY not in text


def test_online_doctor_uses_one_read_only_request():
    save_credentials(Settings(api_key=SecretStr(KEY), region="eu", allow_writes=False))
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/connect/v2/workflows"
        assert request.url.params["limit"] == "1"
        assert request.headers["X-Api-Key"] == KEY
        return httpx.Response(200, json={"data": {"workflows": [], "meta": {"total": 0}}})

    output = io.StringIO()
    assert run_doctor(online=True, output=output, transport=httpx.MockTransport(respond)) == 0
    assert len(calls) == 1
    assert "Read-only API check succeeded" in output.getvalue()
    assert KEY not in output.getvalue()


def test_online_doctor_sanitizes_auth_failure():
    save_credentials(Settings(api_key=SecretStr(KEY), region="us", allow_writes=False))

    def respond(request):
        return httpx.Response(401, text=f"{KEY} rejected")

    output = io.StringIO()
    assert run_doctor(online=True, output=output, transport=httpx.MockTransport(respond)) == 1
    text = output.getvalue()
    assert "401" in text
    assert KEY not in text
    assert "rejected" not in text
