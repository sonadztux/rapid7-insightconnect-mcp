import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import ConfigurationSource, Settings, resolve_settings
from insightconnect_mcp.storage import save_credentials


@pytest.fixture
def stored_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    save_credentials(
        Settings(
            api_key=SecretStr("stored-key"),
            region="eu",
            allow_writes=True,
        )
    )


@pytest.mark.parametrize(
    "environ",
    [
        {"R7_API_KEY": "env-key"},
        {"R7_REGION": "us"},
        {"R7_ALLOW_WRITES": "false"},
        {"R7_API_KEY": "", "R7_REGION": "us"},
        {"R7_API_KEY": "env-key", "R7_REGION": ""},
    ],
)
def test_partial_environment_config_fails_closed_instead_of_using_stored_credentials(
    stored_credentials, environ
):
    with pytest.raises(ValueError, match="R7_API_KEY and R7_REGION are required"):
        Settings.load(environ)


def test_complete_environment_override_can_disable_stored_writes(stored_credentials):
    resolved = Settings.load(
        {
            "R7_API_KEY": "env-key",
            "R7_REGION": "us",
            "R7_ALLOW_WRITES": "false",
        }
    )

    assert resolved.api_key.get_secret_value() == "env-key"
    assert resolved.region == "us"
    assert resolved.allow_writes is False


def test_resolution_reports_no_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty"))
    result = resolve_settings({})
    assert result.source is ConfigurationSource.NONE
    assert result.settings is None
    assert "No credentials found" in (result.error or "")


def test_resolution_reports_stored_credentials(stored_credentials):
    result = resolve_settings({})
    assert result.source is ConfigurationSource.STORED
    assert result.settings is not None
    assert result.settings.region == "eu"
    assert result.error is None


def test_resolution_reports_environment_override(stored_credentials):
    result = resolve_settings(
        {"R7_API_KEY": "env-key", "R7_REGION": "us", "R7_ALLOW_WRITES": "false"}
    )
    assert result.source is ConfigurationSource.ENVIRONMENT
    assert result.settings is not None
    assert result.settings.api_key.get_secret_value() == "env-key"
    assert result.error is None


def test_resolution_reports_partial_environment_error_without_falling_back(stored_credentials):
    result = resolve_settings({"R7_REGION": "us"})
    assert result.source is ConfigurationSource.ENVIRONMENT
    assert result.settings is None
    assert result.error == "R7_API_KEY and R7_REGION are required"
