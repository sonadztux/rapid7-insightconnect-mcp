"""CLI contract: serve stdio by default; configure, doctor, and version as explicit commands."""

import os
import subprocess
import sys

import pytest

COMMAND = str(sys.executable), "-m", "insightconnect_mcp"
CLEAN_ENV = {key: value for key, value in os.environ.items() if not key.startswith("R7_")}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Keep the subprocess away from the developer's real stored credential."""
    monkeypatch.setitem(CLEAN_ENV, "XDG_CONFIG_HOME", str(tmp_path))


def run(*args, stdin=""):
    return subprocess.run(
        [*COMMAND, *args], input=stdin, env=CLEAN_ENV, capture_output=True, text=True, timeout=60
    )


def test_version_prints_package_metadata():
    from importlib.metadata import version

    result = run("--version")
    assert result.returncode == 0
    assert version("rapid7-insightconnect-mcp") in result.stdout


@pytest.mark.parametrize("args", [("--help",), ("help",)])
def test_help_explains_product_commands(args):
    result = run(*args)
    assert result.returncode == 0
    text = result.stdout
    assert "rapid7-insightconnect-mcp" in text
    assert "configure" in text
    assert "doctor" in text
    assert "--version" in text
    # Harness-agnostic guidance, not registration instructions.
    assert "MCP client" in text


@pytest.mark.parametrize(
    "args",
    [
        ("doctor", "--bogus"),
        ("doctor", "--online", "extra"),
        ("configure", "extra"),
        ("setup", "extra"),
        ("--version", "extra"),
    ],
)
def test_invalid_arguments_never_start_server(args):
    result = run(*args)
    assert result.returncode == 2
    assert "Starting unconfigured" not in result.stderr


def test_unknown_command_returns_exit_code_2():
    result = run("bogus")
    assert result.returncode == 2
    assert "Unknown" in result.stderr or "bogus" in result.stderr


def test_setup_alias_forwards_to_configure_with_deprecation_notice():
    result = run("setup", stdin="4\nn\nplaceholder-key\nn\n")
    assert result.returncode == 2  # hidden-input refusal in a piped subprocess
    assert "renamed to `configure`" in result.stdout


def test_setup_wizard_declines_without_a_terminal():
    result = run("setup", stdin="")
    assert result.returncode == 2
    assert "interactive terminal" in result.stdout


def test_configure_declines_hidden_input_in_pipe_fallback():
    result = run("configure", stdin="4\nn\nplaceholder-key\nn\n")
    assert result.returncode == 2
    assert "hidden" in result.stdout
    assert "placeholder-key" not in result.stdout + result.stderr


def test_doctor_offline_reports_unconfigured_without_network():
    result = run("doctor")
    assert result.returncode == 1
    text = result.stdout
    assert "Rapid7 InsightConnect MCP doctor" in text
    assert "not configured" in text.lower()
    # The offline run must not include the online connectivity section verdict as pass.
    assert "✗" in text or "!" in text or "not configured" in text


def test_doctor_online_requires_configuration():
    result = run("doctor", "--online")
    assert result.returncode == 1
    assert "not configured" in result.stdout.lower()


def test_server_starts_unconfigured_and_names_the_setup_route():
    result = run()
    assert result.returncode == 0
    assert "setup" in result.stderr
    assert "R7_API_KEY" not in result.stderr


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 300.0),
        ("15", 15.0),
        ("0.5", 0.5),
        ("", 300.0),
        ("soon", 300.0),
        ("-5", 300.0),
        ("0", 300.0),
        ("nan", 300.0),
        ("inf", 300.0),
    ],
)
def test_setup_timeout_falls_back_on_unusable_values(raw, expected):
    from insightconnect_mcp.server import setup_timeout

    environ = {} if raw is None else {"R7_SETUP_TIMEOUT": raw}
    assert setup_timeout(environ) == expected
