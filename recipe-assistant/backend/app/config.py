from __future__ import annotations

import json
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://recipe:recipe@localhost:5432/recipe"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    environment: str = "development"

    @classmethod
    def from_ha_options(cls) -> Settings:
        """Load settings from Home Assistant /data/options.json if it exists."""
        options_path = Path("/data/options.json")
        if options_path.exists():
            options = json.loads(options_path.read_text())
            return cls(
                database_url="postgresql+asyncpg://recipe:recipe@localhost:5432/recipe",
                anthropic_api_key=options.get("anthropic_api_key", ""),
                openai_api_key=options.get("openai_api_key", ""),
                environment="production",
            )
        return cls()


@lru_cache
def get_settings() -> Settings:
    ha_options = Path("/data/options.json")
    if ha_options.exists():
        return Settings.from_ha_options()
    return Settings()
