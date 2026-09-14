"""Owner-only credential file used when the environment does not carry settings."""

import json
import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from pydantic import SecretStr, ValidationError

from .config import Settings

DIR_MODE = 0o700
FILE_MODE = 0o600
MAX_BYTES = 64 * 1024


def credentials_path() -> Path:
    env = os.environ.get("XDG_CONFIG_HOME")
    # The XDG spec requires an absolute path; a relative one would resolve against
    # whatever directory the server happens to be started from (often a project repo).
    base = Path(env) if env and Path(env).is_absolute() else Path.home() / ".config"
    return base / "rapid7-insightconnect-mcp" / "credentials.json"


def save_credentials(settings: Settings) -> Path:
    path = credentials_path()
    payload = json.dumps(
        {
            "api_key": settings.api_key.get_secret_value(),
            "region": settings.region,
            "allow_writes": settings.allow_writes,
        }
    )
    # Write to a fresh, owner-only temp file and rename it into place: the secret is
    # never briefly readable through a pre-existing file's old permissions, and the
    # rename replaces a symlink at `path` instead of following it to its target.
    with _private_parent(path, create=True) as parent_fd:
        os.fchmod(parent_fd, DIR_MODE)
        tmp_name = f".credentials-{secrets.token_hex(16)}"
        descriptor = os.open(
            tmp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            FILE_MODE,
            dir_fd=parent_fd,
        )
        try:
            with os.fdopen(descriptor, "w") as handle:
                os.fchmod(handle.fileno(), FILE_MODE)
                handle.write(payload)
            os.replace(tmp_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp_name, dir_fd=parent_fd)
            raise
    return path


def _check_directory(descriptor: int, *, final: bool = False) -> None:
    info = os.fstat(descriptor)
    owners = {os.getuid()} if final else {0, os.getuid()}
    # A root-owned ancestor is shared (/tmp, /home) and stays acceptable while it has
    # the sticky bit; anything else must be owner-only.
    shared = info.st_mode & 0o002 and info.st_mode & stat.S_ISVTX and info.st_uid == 0
    if info.st_uid not in owners or (info.st_mode & 0o022 and not shared):
        raise PermissionError(
            "Credential directory ancestry must be trusted and not writable by others"
        )


@contextmanager
def _private_parent(path: Path, *, create: bool = False) -> Iterator[int]:
    parent_fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _check_directory(parent_fd)
        for component in path.parent.parts[1:]:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(component, DIR_MODE, dir_fd=parent_fd)
            child_fd = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
            )
            os.close(parent_fd)
            parent_fd = child_fd
            _check_directory(parent_fd)
        _check_directory(parent_fd, final=True)
        yield parent_fd
    finally:
        os.close(parent_fd)


def _read_private(path: Path) -> str:
    """The stored write policy needs the same trust checks as the credential."""
    with _private_parent(path) as parent_fd:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
        )
        with os.fdopen(descriptor) as handle:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise PermissionError
            return handle.read(MAX_BYTES)


def load_credentials() -> Settings | None:
    path = credentials_path()
    if not path.exists():
        return None
    try:
        content = _read_private(path)
    except OSError:
        raise ValueError(
            f"Stored credentials at {path} must be a regular file only you can read, "
            "in a directory only you can write; fix the permissions or run setup again"
        ) from None
    try:
        stored = json.loads(content)
        writes = stored["allow_writes"]
        if not isinstance(writes, bool):
            raise TypeError("allow_writes must be a JSON boolean")
        return Settings(
            api_key=SecretStr(stored["api_key"]),
            region=stored["region"],
            allow_writes=writes,
        )
    except (ValueError, TypeError, KeyError, ValidationError):
        raise ValueError(f"Stored credentials at {path} are invalid; run setup again") from None
