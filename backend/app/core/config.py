"""Application settings.

Every value comes from the environment. Nothing secret has a working default in
production: `secret_key` defaults to a clearly-labelled development placeholder
and the app refuses to start with it when `environment == "production"`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Deliberately obvious so it can never be mistaken for a real key.
INSECURE_DEV_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    """Runtime configuration, read from `POTENCIA_*` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="POTENCIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    app_version: str = "0.1.0"

    # Required on purpose: a misconfigured deployment must fail loudly rather
    # than silently fall back to a local database nobody can see.
    database_url: str

    secret_key: str = INSECURE_DEV_SECRET
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Where uploaded documents live. Never inside the database, never public.
    storage_root: str = "storage"
    max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        """Allowed browser origins, comma-separated in one env var."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def uses_insecure_secret(self) -> bool:
        return self.secret_key == INSECURE_DEV_SECRET


@lru_cache
def get_settings() -> Settings:
    """Cached settings, so the environment is parsed once per process."""
    return Settings()
