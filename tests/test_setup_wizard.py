import getpass
import io
import sys
import warnings

import httpx
import pytest

from insightconnect_mcp.setup_wizard import REGIONS, run_setup
from insightconnect_mcp.storage import load_credentials

KEY = "wizard-secret-key"


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


def test_wizard_collects_region_writes_and_persists():
    io_args, output = fake_io(["4", "n", "n"])
    assert run_setup(**io_args) == 0
    text = output.getvalue()
    assert load_credentials().region == "eu"
    assert load_credentials().allow_writes is False
    assert "Restart" in text


def test_default_region_and_write_policy():
    io_args, output = fake_io(["", "", "n"])
    assert run_setup(**io_args) == 0
    assert load_credentials().region == "us"
    assert load_credentials().allow_writes is False


def test_write_opt_in_is_explicit():
    io_args, output = fake_io(["1", "y", "n"])
    assert run_setup(**io_args) == 0
    assert load_credentials().allow_writes is True


@pytest.mark.parametrize("bad", ["0", "99", "abc", "-1"])
def test_invalid_region_reprompts(bad):
    io_args, output = fake_io([bad, "2", "n", "n"])
    assert run_setup(**io_args) == 0
    assert load_credentials().region == "us2"


def test_empty_key_reprompts_then_aborts():
    output = io.StringIO()
    attempts = []

    def getpass_fn(prompt):
        attempts.append(prompt)
        return "   "

    replies = iter(["1", "n"])
    code = run_setup(input_fn=lambda prompt: next(replies), getpass_fn=getpass_fn, output=output)
    assert code == 2
    assert len(attempts) == 3
    assert "no API key" in output.getvalue()


def test_no_harness_configuration_is_generated():
    io_args, output = fake_io(["1", "n", "n"])
    assert run_setup(**io_args) == 0
    assert "mcpServers" not in output.getvalue()
    assert "R7_API_KEY" not in output.getvalue()


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

    assert run_setup(input_fn=input_fn, getpass_fn=getpass_fn, output=output) == 0
    assert order.index("key") < order.index("verify")


@pytest.mark.parametrize("tty", [True, False])
def test_setup_aborts_when_the_terminal_cannot_hide_input(monkeypatch, tty):
    """getpass falls back to echoing the key when it cannot disable terminal echo."""
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)

    def echoing(prompt):
        warnings.warn("Can not control echo on the terminal", getpass.GetPassWarning, stacklevel=2)
        return KEY

    io_args, output = fake_io(["1", "n"])
    io_args["getpass_fn"] = echoing
    assert run_setup(**io_args) == 2
    assert "hidden" in output.getvalue()
    assert KEY not in output.getvalue()


def test_key_is_never_echoed_or_returned():
    io_args, output = fake_io(["1", "n", "n"])
    assert run_setup(**io_args) == 0
    assert KEY not in output.getvalue()
    assert "PASTE_YOUR_KEY" not in output.getvalue()


def test_declined_verification_makes_no_request():
    def no_request(request):
        pytest.fail("verification ran without consent")

    io_args, output = fake_io(["1", "n", "n"])
    assert run_setup(**io_args, transport=transport(no_request)) == 0
    assert "not verified" in output.getvalue()


def test_accepted_verification_uses_read_only_route():
    calls = []

    def respond(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/connect/v2/workflows"
        assert request.url.params["limit"] == "1"
        assert request.headers["X-Api-Key"] == KEY
        return httpx.Response(200, json={"data": {"workflows": [], "meta": {"total": 7}}})

    io_args, output = fake_io(["4", "n", "y"])
    assert run_setup(**io_args, transport=transport(respond)) == 0
    assert str(calls[0].url).startswith("https://eu.api.insight.rapid7.com/")
    assert "authentication succeeded" in output.getvalue()
    assert KEY not in output.getvalue()


def test_failed_verification_reports_without_leaking_key():
    def respond(request):
        return httpx.Response(401, text=f"{KEY} rejected by upstream")

    io_args, output = fake_io(["1", "n", "y"])
    assert run_setup(**io_args, transport=transport(respond)) == 1
    text = output.getvalue()
    assert "401" in text
    assert KEY not in text
    assert "rejected by upstream" not in text


def test_non_interactive_input_aborts_cleanly():
    def eof(prompt):
        raise EOFError

    output = io.StringIO()
    code = run_setup(input_fn=eof, getpass_fn=lambda prompt: KEY, output=output)
    assert code == 2
    assert "interactive terminal" in output.getvalue()
