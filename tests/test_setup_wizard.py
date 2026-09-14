import getpass
import io
import sys
import warnings

import httpx
import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
from insightconnect_mcp.setup_wizard import REGIONS, run_configure, run_setup
from insightconnect_mcp.storage import load_credentials, save_credentials

KEY = "wizard-secret-key"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for name in ("R7_API_KEY", "R7_REGION", "R7_ALLOW_WRITES"):
        monkeypatch.delenv(name, raising=False)


def fake_io(answers, key=KEY):
    replies = iter(answers)
    output = io.StringIO()
    return {
        "input_fn": lambda prompt: next(replies),
        "getpass_fn": lambda prompt: key,
        "output": output,
    }, output


def transport(handler):
    return httpx.MockTransport(handler)


def test_regions_match_supported_settings():
    assert REGIONS == ("us", "us2", "us3", "eu", "ca", "au", "ap")


def test_configure_persists_region_key_and_safe_write_default():
    io_args, output = fake_io(["4", "", "n"])
    assert run_configure(**io_args) == 0

    stored = load_credentials()
    assert stored is not None
    assert stored.region == "eu"
    assert stored.api_key.get_secret_value() == KEY
    assert stored.allow_writes is False

    text = output.getvalue()
    assert "Credentials saved" in text
    assert "Writes disabled" in text
    assert KEY not in text
    assert "mcpServers" not in text


def test_write_opt_in_is_explicit_and_persisted():
    io_args, output = fake_io(["1", "y", "n"])
    assert run_configure(**io_args) == 0
    stored = load_credentials()
    assert stored is not None
    assert stored.allow_writes is True
    assert "Writes enabled" in output.getvalue()


@pytest.mark.parametrize("bad", ["0", "99", "abc", "-1"])
def test_invalid_region_reprompts(bad):
    io_args, _ = fake_io([bad, "2", "n", "n"])
    assert run_configure(**io_args) == 0
    stored = load_credentials()
    assert stored is not None
    assert stored.region == "us2"


def test_empty_key_reprompts_then_aborts():
    output = io.StringIO()
    attempts = []

    def getpass_fn(prompt):
        attempts.append(prompt)
        return "   "

    code = run_configure(input_fn=lambda prompt: "1", getpass_fn=getpass_fn, output=output)
    assert code == 2
    assert len(attempts) == 3
    assert "no API key" in output.getvalue()


def test_key_is_requested_before_verification_consent():
    order = []
    output = io.StringIO()
    replies = iter(["1", "n", "n"])

    def input_fn(prompt):
        order.append("verify" if "Verify" in prompt else "other")
        return next(replies)

    def getpass_fn(prompt):
        order.append("key")
        return KEY

    assert run_configure(input_fn=input_fn, getpass_fn=getpass_fn, output=output) == 0
    assert order.index("key") < order.index("verify")


@pytest.mark.parametrize("tty", [True, False])
def test_configure_aborts_when_terminal_cannot_hide_input(monkeypatch, tty):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)

    def echoing(prompt):
        warnings.warn("Can not control echo on the terminal", getpass.GetPassWarning, stacklevel=2)
        return KEY

    io_args, output = fake_io(["1", "n"])
    io_args["getpass_fn"] = echoing
    assert run_configure(**io_args) == 2
    assert "hidden" in output.getvalue()
    assert KEY not in output.getvalue()


def test_key_is_never_echoed_or_returned():
    io_args, output = fake_io(["1", "n", "n"])
    assert run_configure(**io_args) == 0
    assert KEY not in output.getvalue()
    assert "PASTE_YOUR_KEY" not in output.getvalue()


def test_declined_verification_makes_no_request_but_saves():
    def no_request(request):
        pytest.fail("verification ran without consent")

    io_args, output = fake_io(["1", "n", "n"])
    assert run_configure(**io_args, transport=transport(no_request)) == 0
    assert "not checked" in output.getvalue()
    assert load_credentials() is not None


def test_accepted_verification_uses_read_only_route_then_saves():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/connect/v2/workflows"
        assert request.url.params["limit"] == "1"
        assert request.headers["X-Api-Key"] == KEY
        return httpx.Response(200, json={"data": {"workflows": [], "meta": {"total": 7}}})

    io_args, output = fake_io(["4", "n", "y"])
    assert run_configure(**io_args, transport=transport(respond)) == 0
    assert str(calls[0].url).startswith("https://eu.api.insight.rapid7.com/")
    assert "authentication succeeded" in output.getvalue()
    assert KEY not in output.getvalue()
    assert load_credentials() is not None


def test_blank_verification_answer_defaults_to_read_only_check():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data": {"workflows": [], "meta": {"total": 0}}})

    io_args, _ = fake_io(["1", "n", ""])
    assert run_configure(**io_args, transport=transport(respond)) == 0
    assert len(calls) == 1


def test_failed_verification_does_not_replace_existing_credentials():
    save_credentials(Settings(api_key=SecretStr("existing-key"), region="eu", allow_writes=False))

    def respond(request):
        return httpx.Response(401, text=f"{KEY} rejected by upstream")

    io_args, output = fake_io(["1", "n", "y"])
    assert run_configure(**io_args, transport=transport(respond)) == 1
    text = output.getvalue()
    assert "401" in text
    assert KEY not in text
    assert "Existing stored credentials were not changed" in text

    stored = load_credentials()
    assert stored is not None
    assert stored.api_key.get_secret_value() == "existing-key"
    assert stored.region == "eu"


def test_non_interactive_input_aborts_cleanly():
    def eof(prompt):
        raise EOFError

    output = io.StringIO()
    code = run_configure(input_fn=eof, getpass_fn=lambda prompt: KEY, output=output)
    assert code == 2
    assert "interactive terminal" in output.getvalue()


def test_run_setup_remains_a_compatibility_wrapper():
    io_args, _ = fake_io(["1", "n", "n"])
    assert run_setup(**io_args) == 0
    assert load_credentials() is not None
