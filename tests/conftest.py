"""Keep tests isolated from real local Rapid7 configuration."""

import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path, monkeypatch):
    """Never let tests read a developer's credentials or ambient R7_* overrides."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for name in ("R7_API_KEY", "R7_REGION", "R7_ALLOW_WRITES"):
        monkeypatch.delenv(name, raising=False)
