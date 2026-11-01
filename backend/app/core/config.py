"""Application settings.

Every value comes from the environment. Nothing secret has a working default in
production: `secret_key` defaults to a clearly-labelled development placeholder
and the app refuses to start with it when `environment == "production"`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
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

    # Optional. When set, rate-limit counters are shared across workers; when
    # unset, each process keeps its own budget and says so at startup.
    redis_url: str | None = None

    # Load tests and benchmarks switch the limiter off to measure the engine
    # rather than the throttle. It is on by default and must stay on in
    # production.
    rate_limit_enabled: bool = True

    # Where uploaded documents live. Never inside the database, never public.
    storage_root: str = "storage"
    max_upload_bytes: int = 5 * 1024 * 1024

    # Optional Gemini AI rewrite configuration
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "POTENCIA_GEMINI_API_KEY", "Gemini API Key"),
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "POTENCIA_GEMINI_MODEL"),
    )
    gemini_timeout_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("GEMINI_TIMEOUT_SECONDS", "POTENCIA_GEMINI_TIMEOUT_SECONDS"),
    )

    # ClamAV Malware Scanning Configuration
    clamav_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 15
    # When True (or in production), scanner failure fails closed rather than bypassing
    clamav_required: bool = False

    # Document Hardening Limits
    max_pdf_pages: int = 50
    max_docx_entries: int = 1000

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

    @property
    def requires_malware_scan(self) -> bool:
        """In production or when explicitly configured, scanning must never be silently bypassed."""
        return self.clamav_required or self.is_production


@lru_cache
def get_settings() -> Settings:
    """Cached settings, so the environment is parsed once per process."""
    return Settings()
