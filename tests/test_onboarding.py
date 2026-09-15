"""Shared onboarding logic used by both the CLI configure command and the MCP setup tool."""

import asyncio
import getpass
import io
import os

import httpx
import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
from insightconnect_mcp.onboarding import (
    ConfigurationSummary,
    configure_interactively,
    persist_settings,
    summary_of,
    verify_credentials,
)

KEY = "onboarding-secret-key"


def test_verification_defaults_yes(tmp_path, monkeypatch):
    saved_settings(tmp_path, monkeypatch)
    replies = iter(["", "", ""])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={})

    assert (
        configure_interactively(
            input_fn=lambda _: next(replies),
            getpass_fn=lambda _: KEY,
            output=io.StringIO(),
            transport=transport(respond),
        )
        == 0
    )
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["validation", "storage"])
def test_configure_failure_is_sanitized(tmp_path, monkeypatch, failure):
    saved_settings(tmp_path, monkeypatch)
    if failure == "storage":

        def fail(settings):
            raise OSError(KEY)

        monkeypatch.setattr("insightconnect_mcp.onboarding.persist_settings", fail)
    replies = iter(["1", "n", "n"])
    output = io.StringIO()
    assert (
        configure_interactively(
            input_fn=lambda _: next(replies),
            getpass_fn=lambda _: KEY + ("\ninvalid" if failure == "validation" else ""),
            output=output,
        )
        == 1
    )
    assert KEY not in output.getvalue()


def transport(handler):
    return httpx.MockTransport(handler)


def saved_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def test_persist_settings_uses_secure_storage(tmp_path, monkeypatch):
    home = saved_settings(tmp_path, monkeypatch)
    settings = Settings(api_key=SecretStr(KEY), region="eu")
    path = persist_settings(settings)
    assert path.parent.name == "rapid7-insightconnect-mcp"
    assert str(home) in str(path)
    assert path.stat().st_mode & 0o077 == 0


def test_verify_credentials_success_is_read_only():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data": {"workflows": [], "meta": {"total": 0}}})

    settings = Settings(api_key=SecretStr(KEY), region="eu")
    failure = asyncio.run(verify_credentials(settings, transport=transport(respond)))
    assert failure is None
    assert calls[0].method == "GET"
    assert calls[0].url.path == "/connect/v2/workflows"
    assert str(calls[0].url).startswith("https://eu.api.insight.rapid7.com/")


def test_verify_credentials_reports_sanitized_error_without_key():
    def respond(request):
        return httpx.Response(401, text=f"{KEY} rejected by upstream")

    settings = Settings(api_key=SecretStr(KEY), region="us")
    failure = asyncio.run(verify_credentials(settings, transport=transport(respond)))
    assert failure is not None
    assert "401" in failure
    assert KEY not in failure
    assert "rejected by upstream" not in failure


def test_summary_reports_region_writes_and_next_action():
    settings = Settings(api_key=SecretStr(KEY), region="eu")
    summary = summary_of(settings)
    assert isinstance(summary, ConfigurationSummary)
    assert summary.region == "eu"
    assert summary.writes_enabled is False
    assert "list_workflows" in summary.recommended_next_action


def test_configure_interactively_saves_and_reports(tmp_path, monkeypatch):
    saved_settings(tmp_path, monkeypatch)
    replies = iter(["4", "n", "n"])  # region, writes, no verification
    output = io.StringIO()

    def input_fn(prompt):
        return next(replies)

    code = configure_interactively(input_fn=input_fn, getpass_fn=lambda prompt: KEY, output=output)
    text = output.getvalue()
    assert code == 0
    assert "saved" in text.lower()
    assert "eu" in text
    assert KEY not in text
    assert os.environ["XDG_CONFIG_HOME"] == str(tmp_path / "config")


def test_configure_interactively_hides_key_input(tmp_path, monkeypatch):
    saved_settings(tmp_path, monkeypatch)
    replies = iter(["1", "n"])  # region, writes; key attempts happen in getpass
    output = io.StringIO()

    def getpass_fn(prompt):
        # A pipe/IDE fallback cannot disable echo; the command must refuse rather than leak.
        raise getpass.GetPassWarning

    code = configure_interactively(
        input_fn=lambda prompt: next(replies), getpass_fn=getpass_fn, output=output
    )
    assert code == 2
    assert "hidden" in output.getvalue()
    assert KEY not in output.getvalue()


def test_configure_interactively_verification_failure_keeps_previous_credential(
    tmp_path, monkeypatch
):
    saved_settings(tmp_path, monkeypatch)
    good = Settings(api_key=SecretStr("existing-valid-key"), region="us")
    persist_settings(good)

    def respond(request):
        return httpx.Response(401, json={"message": "Unauthorized"})

    replies = iter(["4", "n", "y"])  # region, writes, verification requested
    output = io.StringIO()
    code = configure_interactively(
        input_fn=lambda prompt: next(replies),
        getpass_fn=lambda prompt: KEY,
        output=output,
        transport=transport(respond),
    )
    text = output.getvalue()
    assert code == 1
    assert "verification failed" in text.lower()
    assert KEY not in text
    # The previously stored, valid credential must survive the failed re-configuration.
    assert load_stored_key() == "existing-valid-key"


def load_stored_key():
    from insightconnect_mcp.storage import load_credentials

    stored = load_credentials()
    assert stored is not None
    return stored.api_key.get_secret_value()


def test_configure_interactively_verifies_before_save_when_requested(tmp_path, monkeypatch):
    saved_settings(tmp_path, monkeypatch)

    def respond(request):
        return httpx.Response(200, json={"data": {"workflows": [], "meta": {"total": 3}}})

    replies = iter(["2", "y", "y"])
    output = io.StringIO()
    code = configure_interactively(
        input_fn=lambda prompt: next(replies),
        getpass_fn=lambda prompt: KEY,
        output=output,
        transport=transport(respond),
    )
    text = output.getvalue()
    assert code == 0
    assert "authentication succeeded" in text.lower()
    assert "saved" in text.lower()
    assert load_stored_key() == KEY


def test_configure_interactively_aborts_without_interactive_input(tmp_path, monkeypatch):
    saved_settings(tmp_path, monkeypatch)

    def eof(prompt):
        raise EOFError

    output = io.StringIO()
    code = configure_interactively(input_fn=eof, getpass_fn=lambda prompt: KEY, output=output)
    assert code == 2
    assert "interactive terminal" in output.getvalue()
    assert not (tmp_path / "config" / "rapid7-insightconnect-mcp" / "credentials.json").exists()


def test_configure_interactively_rejects_unexpected_harness_snippet_output(tmp_path, monkeypatch):
    """No harness config generation may remain in the configure output."""
    saved_settings(tmp_path, monkeypatch)
    replies = iter(["1", "n", "n"])
    output = io.StringIO()
    configure_interactively(
        input_fn=lambda prompt: next(replies), getpass_fn=lambda prompt: KEY, output=output
    )
    text = output.getvalue()
    assert "mcpServers" not in text
    assert "R7_API_KEY" not in text
    assert "PLACEHOLDER" not in text
