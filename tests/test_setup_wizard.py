import io
import json
from pathlib import Path

import httpx
import pytest

from insightconnect_mcp.setup_wizard import REGIONS, run_setup

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


def test_wizard_collects_region_writes_and_prints_snippet():
    io_args, output = fake_io(["4", "n", "n"])
    assert run_setup(**io_args) == 0
    text = output.getvalue()
    assert '"R7_REGION": "eu"' in text
    assert '"R7_ALLOW_WRITES": "false"' in text
    assert "rapid7-insightconnect" in text


def test_default_region_and_write_policy():
    io_args, output = fake_io(["", "", ""])
    assert run_setup(**io_args) == 0
    assert '"R7_REGION": "us"' in output.getvalue()
    assert '"R7_ALLOW_WRITES": "false"' in output.getvalue()


def test_write_opt_in_is_explicit():
    io_args, output = fake_io(["1", "y", "n"])
    assert run_setup(**io_args) == 0
    assert '"R7_ALLOW_WRITES": "true"' in output.getvalue()


@pytest.mark.parametrize("bad", ["0", "99", "abc", "-1"])
def test_invalid_region_reprompts(bad):
    io_args, output = fake_io([bad, "2", "n", "n"])
    assert run_setup(**io_args) == 0
    assert '"R7_REGION": "us2"' in output.getvalue()


def test_empty_key_reprompts_then_aborts():
    output = io.StringIO()
    attempts = []

    def getpass_fn(prompt):
        attempts.append(prompt)
        return "   "

    code = run_setup(input_fn=lambda prompt: "1", getpass_fn=getpass_fn, output=output)
    assert code == 2
    assert len(attempts) == 3
    assert "no API key" in output.getvalue()


def test_snippet_command_is_an_absolute_launcher_path():
    io_args, output = fake_io(["1", "n", "n"])
    assert run_setup(**io_args) == 0
    text = output.getvalue()
    snippet = json.loads(text[text.index("{") : text.rindex("}") + 1])
    path = Path(snippet["mcpServers"]["rapid7-insightconnect"]["command"])
    assert path.is_absolute()
    assert path.exists()


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


def test_key_is_never_echoed_or_returned():
    io_args, output = fake_io(["1", "n", "n"])
    assert run_setup(**io_args) == 0
    assert KEY not in output.getvalue()
    assert "PASTE_YOUR_KEY" in output.getvalue()


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
    assert "verified" in output.getvalue()
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
