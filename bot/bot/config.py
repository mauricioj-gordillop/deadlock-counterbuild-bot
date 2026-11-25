"""Unified Discord bot configuration powered by Databricks Gold tables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str = ""
    discord_guild_id: int | None = None

    databricks_server_hostname: str = ""
    databricks_http_path: str = ""
    databricks_token: str = ""
    databricks_catalog: str = "workspace"
    databricks_schema: str = "deadlock"

    refresh_interval_hours: float = 12.0
    default_limit: int = 3
    max_limit: int = 5
    health_port: int = 8080
    log_level: str = "INFO"

    @field_validator("discord_guild_id", mode="before")
    @classmethod
    def _empty_guild_to_none(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return value


@lru_cache(maxsize=1)
def get_bot_settings() -> BotSettings:
    """Return cached bot settings."""
    return BotSettings()
