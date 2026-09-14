"""Owner-only credential file used when the environment does not carry settings."""

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path

from pydantic import SecretStr, ValidationError

from .config import Settings

DIR_MODE = 0o700
FILE_MODE = 0o600


def credentials_path() -> Path:
    env = os.environ.get("XDG_CONFIG_HOME")
    # The XDG spec requires an absolute path; a relative one would resolve against
    # whatever directory the server happens to be started from (often a project repo).
    base = Path(env) if env and Path(env).is_absolute() else Path.home() / ".config"
    return base / "rapid7-insightconnect-mcp" / "credentials.json"


def save_credentials(settings: Settings) -> Path:
    path = credentials_path()
    path.parent.mkdir(parents=True, mode=DIR_MODE, exist_ok=True)
    path.parent.chmod(DIR_MODE)
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
    descriptor, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".credentials-")
    try:
        os.fchmod(descriptor, FILE_MODE)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise
    return path


def load_credentials() -> Settings | None:
    path = credentials_path()
    if not path.exists():
        return None
    try:
        stored = json.loads(path.read_text())
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
