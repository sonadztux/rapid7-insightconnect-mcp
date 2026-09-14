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


@pytest.mark.parametrize("ancestor", [False, True])
def test_save_rejects_symlink_parent_without_modifying_target(home, ancestor):
    path = save_credentials(settings())
    parent = path.parent.parent if ancestor else path.parent
    target = parent.with_name("redirected")
    parent.rename(target)
    parent.symlink_to(target, target_is_directory=True)
    saved = target / "rapid7-insightconnect-mcp" / path.name if ancestor else target / path.name
    before = saved.read_bytes()
    mode = target.stat().st_mode
    with pytest.raises(OSError):
        save_credentials(settings(api_key=SecretStr("replacement-key")))
    assert saved.read_bytes() == before
    assert target.stat().st_mode == mode
    assert list(saved.parent.iterdir()) == [saved]


@pytest.mark.parametrize("ancestor", [False, True])
def test_save_rejects_writable_parent_without_chmod_or_write(home, ancestor):
    path = save_credentials(settings())
    parent = path.parent.parent if ancestor else path.parent
    parent.chmod(0o777)
    before = path.read_bytes()
    with pytest.raises(PermissionError):
        save_credentials(settings(api_key=SecretStr("replacement-key")))
    assert path.read_bytes() == before
    assert stat.S_IMODE(parent.stat().st_mode) == 0o777
    assert list(path.parent.iterdir()) == [path]


def test_save_rejects_foreign_owner_before_mutation(home, monkeypatch):
    import os
    from types import SimpleNamespace

    path = save_credentials(settings())
    before = path.read_bytes()
    original = os.fstat
    inode = path.parent.stat().st_ino

    def foreign_owner(fd):
        info = original(fd)
        if info.st_ino == inode:
            return SimpleNamespace(st_uid=os.getuid() + 1, st_mode=info.st_mode)
        return info

    monkeypatch.setattr(os, "fstat", foreign_owner)
    with pytest.raises(PermissionError):
        save_credentials(settings(api_key=SecretStr("replacement-key")))
    assert path.read_bytes() == before
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_load_rejects_credentials_readable_by_other_accounts(home):
    save_credentials(settings())
    credentials_path().chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        load_credentials()


def test_load_refuses_to_follow_a_symlinked_credential_file(home):
    save_credentials(settings())
    path = credentials_path()
    elsewhere = home / "elsewhere.json"
    path.replace(elsewhere)
    elsewhere.chmod(stat.S_IRUSR | stat.S_IWUSR)
    path.symlink_to(elsewhere)
    with pytest.raises(ValueError, match="permissions"):
        load_credentials()


def test_load_rejects_symlinked_parent(home):
    save_credentials(settings())
    parent = credentials_path().parent
    target = parent.with_name("elsewhere")
    parent.rename(target)
    parent.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="permissions"):
        load_credentials()


def test_private_read_opens_nonblocking(home, monkeypatch):
    import os

    from insightconnect_mcp.storage import _read_private

    save_credentials(settings())
    original = os.open

    def checked_open(path, flags, *args, **kwargs):
        assert flags & os.O_NOFOLLOW
        if not flags & os.O_DIRECTORY:
            assert flags & os.O_NONBLOCK
            assert kwargs.get("dir_fd") is not None
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", checked_open)
    assert KEY in _read_private(credentials_path())


def test_load_rejects_a_config_directory_other_accounts_can_write(home):
    """A writable directory lets another account swap the file, including allow_writes."""
    save_credentials(settings())
    credentials_path().parent.chmod(0o707)
    with pytest.raises(ValueError, match="permissions"):
        load_credentials()


def test_shared_sticky_ancestors_are_accepted(tmp_path, monkeypatch):
    """XDG_CONFIG_HOME under /tmp (sticky, root-owned) must keep working: only the
    user-owned segment between shared ancestors and the config dir needs trust."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "shared" / "config"))
    save_credentials(settings())
    loaded = load_credentials()
    assert loaded.api_key.get_secret_value() == KEY
    # ...while a non-sticky shared ancestor still fails, because anyone could swap it.
    loose = tmp_path / "loose" / "config"
    loose.mkdir(parents=True)
    loose.chmod(0o707)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(loose))
    with pytest.raises((OSError, ValueError)):
        save_credentials(settings())
