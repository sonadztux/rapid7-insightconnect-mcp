"""Owner-only credential file used when the environment does not carry settings."""

import json
import os
from pathlib import Path

from pydantic import SecretStr, ValidationError

from .config import Settings

DIR_MODE = 0o700
FILE_MODE = 0o600


def credentials_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "rapid7-insightconnect-mcp" / "credentials.json"


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
    # Create with restrictive permissions before any secret reaches the filesystem.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(payload)
    path.chmod(FILE_MODE)
    return path


def load_credentials() -> Settings | None:
    path = credentials_path()
    if not path.exists():
        return None
    try:
        stored = json.loads(path.read_text())
        return Settings(
            api_key=SecretStr(stored["api_key"]),
            region=stored["region"],
            allow_writes=bool(stored.get("allow_writes", False)),
        )
    except (ValueError, TypeError, KeyError, ValidationError):
        raise ValueError(f"Stored credentials at {path} are invalid; run setup again") from None
