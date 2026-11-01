"""Application settings loaded from the environment (docs/API.md §1).

Defaults are explicitly safe for local development, and every production check
refuses to boot if a production requirement is violated.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEV_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POTENCIA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "development"
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # Database
    database_url: str = (
        "postgresql+psycopg://potencia:potencia@localhost:5432/potencia"
    )

    # Security
    secret_key: str = INSECURE_DEV_SECRET
    cors_origins: str = "http://localhost:5173"

    # Token lifetimes (minutes)
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14

    # Rate limiting
    rate_limit_enabled: bool = True
    redis_url: str | None = None

    # Storage
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

    # OCR Configuration
    ocr_enabled: bool = True
    ocr_tesseract_cmd: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POTENCIA_OCR_TESSERACT_CMD", "OCR_TESSERACT_CMD"),
    )
    ocr_language: str = Field(
        default="eng",
        validation_alias=AliasChoices("POTENCIA_OCR_LANGUAGE", "OCR_LANGUAGE"),
    )
    ocr_timeout_seconds: float = 30.0
    ocr_dpi: int = 200
    ocr_min_confidence: float = 40.0
    ocr_deskew_enabled: bool = True

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
