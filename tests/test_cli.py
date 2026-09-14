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


def test_setup_subcommand_refuses_echoing_pipe_fallback():
    result = run("setup", stdin="4\nn\nplaceholder-key\nn\n")
    assert result.returncode == 2
    assert "hidden" in result.stdout
    assert "placeholder-key" not in result.stdout + result.stderr


def test_setup_wizard_declines_without_a_terminal():
    result = run("setup", stdin="")
    assert result.returncode == 2
    assert "interactive terminal" in result.stdout


@pytest.mark.parametrize("args", [("--help",), ("help",), ("bogus",)])
def test_usage_mentions_both_modes(args):
    result = run(*args)
    assert "setup" in result.stdout + result.stderr
    assert "needs R7_" not in result.stdout + result.stderr
    assert result.returncode == (0 if args[0] in {"--help", "help"} else 2)


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
    assert "setup" in result.stderr
    assert "R7_API_KEY" not in result.stderr
