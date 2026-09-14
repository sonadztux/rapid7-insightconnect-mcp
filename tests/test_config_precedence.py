import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
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
