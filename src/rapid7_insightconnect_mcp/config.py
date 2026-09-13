"""Environment-only configuration; API hosts are never supplied by tool callers."""

import os
from collections.abc import Mapping
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

Region = Literal["us", "us2", "us3", "eu", "ca", "au", "ap"]


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
        """Environment wins so operators can override a stored credential."""
        from .storage import load_credentials

        env = os.environ if environ is None else environ
        if env.get("R7_API_KEY") and env.get("R7_REGION"):
            return cls.from_env(env)
        stored = load_credentials()
        if stored is None:
            raise ValueError(
                "No credentials found. Call the setup tool, or run "
                "`rapid7-insightconnect-mcp setup` in a terminal"
            )
        return cls.model_validate(stored.model_dump())

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
