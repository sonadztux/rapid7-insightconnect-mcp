import io

import httpx
import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
from insightconnect_mcp.diagnostics import CheckStatus, collect_diagnostics, run_doctor
from insightconnect_mcp.storage import credentials_path, save_credentials

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
    assert "Source: none" in text
    assert "configuration required" in text
    assert KEY not in text


def test_local_doctor_reports_stored_source_region_write_policy_and_storage_validation():
    save_credentials(Settings(api_key=SecretStr(KEY), region="eu", allow_writes=False))
    output = io.StringIO()
    assert run_doctor(output=output) == 0
    text = output.getvalue()
    assert "Source: stored credentials" in text
    assert "Credential storage validated" in text
    assert "Region: eu" in text
    assert "Writes disabled" in text
    assert "Not checked" in text
    assert KEY not in text


def test_local_doctor_reports_environment_source_without_claiming_storage_validation(monkeypatch):
    monkeypatch.setenv("R7_API_KEY", KEY)
    monkeypatch.setenv("R7_REGION", "us2")
    monkeypatch.setenv("R7_ALLOW_WRITES", "false")

    output = io.StringIO()
    assert run_doctor(output=output) == 0
    text = output.getvalue()
    assert "Source: environment" in text
    assert "Region: us2" in text
    assert "Credential storage validated" not in text
    assert KEY not in text


def test_partial_environment_doctor_fails_closed_even_when_stored_credentials_exist(monkeypatch):
    save_credentials(Settings(api_key=SecretStr("stored-key"), region="eu", allow_writes=False))
    monkeypatch.setenv("R7_REGION", "us")

    output = io.StringIO()
    assert run_doctor(output=output) == 1
    text = output.getvalue()
    assert "Source: environment" in text
    assert "R7_API_KEY and R7_REGION are required" in text
    assert "Region: eu" not in text
    assert "stored-key" not in text


def test_local_doctor_rejects_unsafe_stored_credential_permissions():
    save_credentials(Settings(api_key=SecretStr(KEY), region="eu", allow_writes=False))
    credentials_path().chmod(0o644)

    output = io.StringIO()
    assert run_doctor(output=output) == 1
    text = output.getvalue()
    assert "Source: stored credentials" in text
    assert "configuration required" in text
    assert KEY not in text


def test_collect_diagnostics_returns_structured_checks():
    save_credentials(Settings(api_key=SecretStr(KEY), region="eu", allow_writes=False))
    checks = collect_diagnostics()
    assert checks
    assert all(check.status in CheckStatus for check in checks)
    assert any(check.name == "configuration-source" for check in checks)
    connectivity = next(check for check in checks if check.name == "rapid7-connectivity")
    assert connectivity.status is CheckStatus.WARNING
    assert "doctor --online" in (connectivity.remediation or "")


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


def test_online_doctor_distinguishes_authentication_failure():
    save_credentials(Settings(api_key=SecretStr(KEY), region="us", allow_writes=False))

    def respond(request):
        return httpx.Response(401, text=f"{KEY} rejected")

    output = io.StringIO()
    assert run_doctor(online=True, output=output, transport=httpx.MockTransport(respond)) == 1
    text = output.getvalue()
    assert "Authentication failed" in text
    assert "401" in text
    assert "API key and region" in text
    assert KEY not in text
    assert "rejected" not in text


def test_online_doctor_distinguishes_authorization_failure():
    save_credentials(Settings(api_key=SecretStr(KEY), region="us", allow_writes=False))

    def respond(request):
        return httpx.Response(403, text="forbidden")

    output = io.StringIO()
    assert run_doctor(online=True, output=output, transport=httpx.MockTransport(respond)) == 1
    text = output.getvalue()
    assert "Authorization failed" in text
    assert "403" in text
    assert "permissions" in text
    assert KEY not in text


def test_online_doctor_distinguishes_network_failure():
    save_credentials(Settings(api_key=SecretStr(KEY), region="us", allow_writes=False))

    def respond(request):
        raise httpx.ConnectError("network exploded", request=request)

    output = io.StringIO()
    assert run_doctor(online=True, output=output, transport=httpx.MockTransport(respond)) == 1
    text = output.getvalue()
    assert "Connection failed" in text
    assert "network" in text.lower()
    assert KEY not in text
