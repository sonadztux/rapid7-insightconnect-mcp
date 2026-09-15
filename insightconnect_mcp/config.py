"""Configuration resolution; API hosts are never supplied by tool callers."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError, field_validator

Region = Literal["us", "us2", "us3", "eu", "ca", "au", "ap"]
ENV_SETTINGS = ("R7_API_KEY", "R7_REGION", "R7_ALLOW_WRITES")


class ConfigurationSource(StrEnum):
    ENVIRONMENT = "environment"
    STORED = "stored credentials"
    NONE = "none"


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
    def load(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Resolve settings, failing closed when the selected source is invalid."""
        resolution = resolve_settings(environ)
        if resolution.settings is None:
            raise ValueError(resolution.error or "Rapid7 configuration is unavailable")
        return cls.model_validate(resolution.settings.model_dump())

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Self:
        env = os.environ if environ is None else environ
        if not env.get("R7_API_KEY") or not env.get("R7_REGION"):
            raise ValueError("R7_API_KEY and R7_REGION are required")
        writes = env.get("R7_ALLOW_WRITES", "false")
        if writes not in {"true", "false"}:
            raise ValueError("R7_ALLOW_WRITES must be true or false")
        return cls(
            api_key=SecretStr(env["R7_API_KEY"]),
            region=env["R7_REGION"],  # type: ignore[arg-type]
            allow_writes=writes == "true",
        )


@dataclass(frozen=True)
class ConfigurationResolution:
    source: ConfigurationSource
    settings: Settings | None
    error: str | None = None


def resolve_settings(environ: Mapping[str, str] | None = None) -> ConfigurationResolution:
    """Inspect configuration selection without hiding why resolution failed."""
    from .storage import load_credentials

    env = os.environ if environ is None else environ
    if any(name in env for name in ENV_SETTINGS):
        try:
            settings = Settings.from_env(env)
        except ValidationError:
            return ConfigurationResolution(
                ConfigurationSource.ENVIRONMENT,
                None,
                "Invalid environment configuration: use a nonempty printable ASCII API key, "
                "a supported R7_REGION, and R7_ALLOW_WRITES=true or false.",
            )
        except ValueError as error:
            return ConfigurationResolution(ConfigurationSource.ENVIRONMENT, None, str(error))
        return ConfigurationResolution(ConfigurationSource.ENVIRONMENT, settings)

    try:
        stored = load_credentials()
    except ValueError as error:
        return ConfigurationResolution(ConfigurationSource.STORED, None, str(error))
    if stored is None:
        return ConfigurationResolution(
            ConfigurationSource.NONE,
            None,
            "No credentials found. Call the setup tool, or run "
            "`uvx rapid7-insightconnect-mcp configure` in a terminal",
        )
    return ConfigurationResolution(ConfigurationSource.STORED, stored)
