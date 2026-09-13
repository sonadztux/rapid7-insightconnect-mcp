import os
import subprocess
import sys

import pytest

COMMAND = str(sys.executable), "-m", "rapid7_insightconnect_mcp"
CLEAN_ENV = {key: value for key, value in os.environ.items() if not key.startswith("R7_")}


def run(*args, stdin=""):
    return subprocess.run(
        [*COMMAND, *args], input=stdin, env=CLEAN_ENV, capture_output=True, text=True, timeout=60
    )


def test_setup_subcommand_runs_wizard_without_credentials():
    result = run("setup", stdin="4\nn\nplaceholder-key\nn\n")
    assert result.returncode == 0
    assert '"R7_REGION": "eu"' in result.stdout
    assert "placeholder-key" not in result.stdout
    assert "no request was made" in result.stdout


def test_setup_wizard_declines_without_a_terminal():
    result = run("setup", stdin="")
    assert result.returncode == 2
    assert "interactive terminal" in result.stdout


@pytest.mark.parametrize("args", [("--help",), ("help",), ("bogus",)])
def test_usage_mentions_both_modes(args):
    result = run(*args)
    assert "setup" in result.stdout + result.stderr
    assert result.returncode == (0 if args[0] in {"--help", "help"} else 2)


def test_server_starts_unconfigured_and_names_the_setup_route():
    result = run()
    assert result.returncode == 0
    assert "setup" in result.stderr
    assert "R7_API_KEY" not in result.stderr
