import os
import subprocess
import sys

import pytest

COMMAND = str(sys.executable), "-m", "insightconnect_mcp"
CLEAN_ENV = {key: value for key, value in os.environ.items() if not key.startswith("R7_")}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Keep subprocesses away from the developer's real stored credential."""
    monkeypatch.setitem(CLEAN_ENV, "XDG_CONFIG_HOME", str(tmp_path / "config"))


def run(*args, stdin=""):
    return subprocess.run(
        [*COMMAND, *args], input=stdin, env=CLEAN_ENV, capture_output=True, text=True, timeout=60
    )


def test_configure_refuses_echoing_pipe_fallback():
    result = run("configure", stdin="4\nn\nplaceholder-key\nn\n")
    assert result.returncode == 2
    assert "hidden" in result.stdout
    assert "placeholder-key" not in result.stdout + result.stderr


def test_setup_alias_points_to_configure_and_refuses_non_tty_key_input():
    result = run("setup", stdin="4\nn\nplaceholder-key\nn\n")
    assert result.returncode == 2
    assert "renamed to `configure`" in result.stderr
    assert "placeholder-key" not in result.stdout + result.stderr


def test_configure_declines_without_an_interactive_terminal():
    result = run("configure", stdin="")
    assert result.returncode == 2
    assert "interactive terminal" in result.stdout


@pytest.mark.parametrize("args", [("--help",), ("help",)])
def test_help_describes_harness_agnostic_commands(args):
    result = run(*args)
    text = result.stdout + result.stderr
    assert result.returncode == 0
    assert "configure" in text
    assert "doctor" in text
    assert "--version" in text
    assert "MCP client's own MCP" in text


def test_version_prints_package_version():
    result = run("--version")
    assert result.returncode == 0
    assert result.stdout.strip()
    assert "Rapid7" not in result.stderr


@pytest.mark.parametrize("args", [("bogus",), ("doctor", "--wat"), ("configure", "extra")])
def test_invalid_cli_arguments_return_two(args):
    result = run(*args)
    assert result.returncode == 2
    assert "Unknown or invalid arguments" in result.stderr


def test_doctor_is_local_and_reports_missing_configuration():
    result = run("doctor")
    assert result.returncode == 1
    assert "doctor" in result.stdout
    assert "configuration required" in result.stdout
    assert "--online" not in result.stderr


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


def test_server_starts_unconfigured_and_names_the_setup_route():
    result = run()
    assert result.returncode == 0
    assert "setup tool" in result.stderr
    assert "rapid7-insightconnect-mcp configure" in result.stderr
    assert "rapid7-insightconnect-mcp setup" not in result.stderr
    assert "R7_API_KEY" not in result.stderr


class _InteractiveStdin:
    def isatty(self) -> bool:
        return True


def test_bare_cli_in_interactive_terminal_shows_mcp_client_guidance(monkeypatch, capsys):
    from insightconnect_mcp import cli

    monkeypatch.setattr(cli.sys, "argv", ["rapid7-insightconnect-mcp"])
    monkeypatch.setattr(cli.sys, "stdin", _InteractiveStdin())

    def unexpected_serve() -> None:
        pytest.fail("interactive terminal should not start the stdio MCP server")

    monkeypatch.setattr(cli, "serve", unexpected_serve)
    cli.main()

    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "MCP client" in text
    assert "uvx rapid7-insightconnect-mcp" in text
    assert "configure" in text
    assert "--version" in text
