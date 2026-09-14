import json
import stat
from pathlib import Path

import pytest
from pydantic import SecretStr

from insightconnect_mcp.config import Settings
from insightconnect_mcp.storage import credentials_path, load_credentials, save_credentials

KEY = "stored-secret-key"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def settings(**overrides):
    values = {"api_key": SecretStr(KEY), "region": "eu", "allow_writes": False}
    return Settings(**{**values, **overrides})


def test_path_lives_outside_the_project(home):
    assert credentials_path().parent.name == "rapid7-insightconnect-mcp"
    assert str(home) in str(credentials_path())


def test_saved_file_and_directory_are_owner_only(home):
    path = save_credentials(settings())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_round_trip_preserves_region_and_write_policy(home):
    save_credentials(settings(region="au", allow_writes=True))
    loaded = load_credentials()
    assert loaded.region == "au"
    assert loaded.allow_writes is True
    assert loaded.api_key.get_secret_value() == KEY


def test_missing_file_returns_none(home):
    assert load_credentials() is None


def test_rewrite_replaces_previous_key_without_leaving_copies(home):
    save_credentials(settings())
    path = save_credentials(settings(api_key=SecretStr("second-key")))
    assert load_credentials().api_key.get_secret_value() == "second-key"
    assert KEY not in path.read_text()
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", "null", '{"region": "eu"}', '{"api_key": "k", "region": "mars"}'],
)
def test_corrupt_or_invalid_file_is_rejected(home, content):
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    with pytest.raises(ValueError, match="credentials"):
        load_credentials()


def test_environment_takes_precedence_over_stored_file(home):
    save_credentials(settings(region="eu"))
    resolved = Settings.load({"R7_API_KEY": "env-key", "R7_REGION": "us"})
    assert resolved.api_key.get_secret_value() == "env-key"
    assert resolved.region == "us"


def test_stored_file_is_used_when_environment_is_empty(home):
    save_credentials(settings(region="ca", allow_writes=True))
    resolved = Settings.load({})
    assert resolved.region == "ca"
    assert resolved.allow_writes is True


@pytest.mark.parametrize(
    "content",
    [
        '{"api_key": "k", "region": "us", "allow_writes": "false"}',
        '{"api_key": "k", "region": "us", "allow_writes": "0"}',
        '{"api_key": "k", "region": "us", "allow_writes": 1}',
        '{"api_key": "k", "region": "us", "allow_writes": null}',
    ],
)
def test_nonboolean_write_policy_is_rejected_not_coerced_true(home, content):
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    with pytest.raises(ValueError, match="credentials"):
        load_credentials()


def test_no_environment_and_no_file_raises(home):
    with pytest.raises(ValueError, match="setup"):
        Settings.load({})


def test_saved_payload_contains_no_extra_fields(home):
    path = save_credentials(settings())
    assert set(json.loads(path.read_text())) == {"api_key", "region", "allow_writes"}


def test_relative_xdg_config_home_is_ignored(tmp_path, monkeypatch):
    """A relative XDG_CONFIG_HOME would otherwise resolve against the server's cwd,
    which is often a project checkout rather than the user's actual config dir."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/config")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert credentials_path() == tmp_path / ".config" / "rapid7-insightconnect-mcp" / (
        "credentials.json"
    )


def test_save_replaces_a_symlink_at_the_target_instead_of_following_it(home):
    path = credentials_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    target = home / "elsewhere.txt"
    target.write_text("untouched")
    path.symlink_to(target)

    save_credentials(settings())

    assert target.read_text() == "untouched"
    assert not path.is_symlink()
    assert load_credentials().api_key.get_secret_value() == KEY


def test_save_does_not_leave_a_partial_file_on_write_failure(home, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("os.fchmod", boom)
    with pytest.raises(OSError):
        save_credentials(settings())
    assert list(credentials_path().parent.iterdir()) == []
