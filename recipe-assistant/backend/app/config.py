from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # picnic_email has validation_alias=AliasChoices("PICNIC_MAIL", "PICNIC_EMAIL")
        # for env var support. Without populate_by_name=True, the alias becomes
        # EXCLUSIVE: explicit kwargs passed by from_ha_options() are silently
        # ignored, and the field falls back to "" — breaking the HA addon path
        # where credentials come from /data/options.json, not env vars.
        populate_by_name=True,
    )

    database_url: str = "postgresql+asyncpg://recipe:recipe@localhost:5432/recipe"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    picnic_email: str = Field(default="", validation_alias=AliasChoices("PICNIC_MAIL", "PICNIC_EMAIL"))
    picnic_password: str = ""
    picnic_country_code: str = "DE"
    environment: str = "development"

    @classmethod
    def from_ha_options(cls, options_path: Path | None = None) -> Settings:
        """Load settings from Home Assistant /data/options.json if it exists.

        The path is parameterized so tests can point it at a temporary file;
        production callers pass nothing and get the real HA addon location.
        """
        if options_path is None:
            options_path = Path("/data/options.json")
        if options_path.exists():
            options = json.loads(options_path.read_text())
            return cls(
                database_url="postgresql+asyncpg://recipe:recipe@localhost:5432/recipe",
                anthropic_api_key=options.get("anthropic_api_key", ""),
                openai_api_key=options.get("openai_api_key", ""),
                picnic_email=options.get("picnic_email", "") or options.get("picnic_mail", ""),
                picnic_password=options.get("picnic_password", ""),
                picnic_country_code=options.get("picnic_country_code", "DE"),
                environment="production",
            )
        return cls()


@lru_cache
def get_settings() -> Settings:
    ha_options = Path("/data/options.json")
    if ha_options.exists():
        return Settings.from_ha_options()
    return Settings()
