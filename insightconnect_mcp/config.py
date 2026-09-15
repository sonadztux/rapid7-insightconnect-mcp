"""Fail-closed configuration; API hosts are never supplied by tool callers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

Region = Literal["us", "us2", "us3", "eu", "ca", "au", "ap"]
ENV_SETTINGS = ("R7_API_KEY", "R7_REGION", "R7_ALLOW_WRITES")


class ConfigurationSource(StrEnum):
    ENVIRONMENT = "environment"
    STORED = "stored"
    NONE = "none"


class ConfigurationResolution(BaseModel):
    """Inspectable outcome of configuration lookup, for CLI/doctor reporting."""

    source: ConfigurationSource
    settings: Settings | None = None
    error: str | None = None


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    api_key: SecretStr
    region: Region
    allow_writes: bool = False

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value()
        if not key.strip() or not key.isascii() or any(ord(char) < 33 for char in key):
            raise ValueError("API key must be nonempty printable ASCII without whitespace")
        return value

    @property
    def base_url(self) -> str:
        return f"https://{self.region}.api.insight.rapid7.com/"

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Environment wins so operators can override a stored credential."""
        resolution = resolve_settings(environ)
        if resolution.settings is None:
            raise ValueError(resolution.error or "No credentials found")
        return resolution.settings

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        env = os.environ if environ is None else environ
        if not env.get("R7_API_KEY") or not env.get("R7_REGION"):
            raise ValueError("R7_API_KEY and R7_REGION are required")
        writes = env.get("R7_ALLOW_WRITES", "false")
        if writes not in {"true", "false"}:
            raise ValueError("R7_ALLOW_WRITES must be true or false")
        try:
            return cls(
                api_key=SecretStr(env["R7_API_KEY"]),
                region=env["R7_REGION"],  # type: ignore[arg-type]
                allow_writes=writes == "true",
            )
        except ValidationError:
            raise ValueError("Invalid Rapid7 API key or region configuration") from None


def resolve_settings(environ: Mapping[str, str] | None = None) -> ConfigurationResolution:
    """Resolve settings with fail-closed env precedence, reporting the outcome instead of raising.

    The presence of any R7_* variable selects environment configuration; an incomplete
    env configuration must not fall back to stored credentials.
    """
    from .storage import load_credentials

    env = os.environ if environ is None else environ
    if any(name in env for name in ENV_SETTINGS):
        try:
            return ConfigurationResolution(
                source=ConfigurationSource.ENVIRONMENT, settings=Settings.from_env(env)
            )
        except ValueError:
            return ConfigurationResolution(
                source=ConfigurationSource.ENVIRONMENT,
                error="Invalid environment configuration: R7_API_KEY and R7_REGION are required; "
                "use a supported region and R7_ALLOW_WRITES=true or false. "
                "No stored credentials were used.",
            )
    try:
        stored = load_credentials()
    except (ValueError, OSError):
        return ConfigurationResolution(
            source=ConfigurationSource.STORED,
            error="Stored credentials are invalid or unsafe; check private file ownership, "
            "permissions and directory ancestry, or run configure again.",
        )
    if stored is None:
        return ConfigurationResolution(
            source=ConfigurationSource.NONE,
            error="No credentials found. Call the setup tool, or run "
            "`rapid7-insightconnect-mcp configure` in a terminal",
        )
    return ConfigurationResolution(source=ConfigurationSource.STORED, settings=stored)
