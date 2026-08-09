from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database
    database_url: str = (
        "postgresql+psycopg2://pokegrading:changeme@localhost:5432/pokegrading_dev"
    )

    # JWT
    jwt_secret_key: str = "change-this-secret-before-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Application
    app_title: str = "PokéGrading API"
    app_version: str = "1.0.0"
    app_debug: bool = False
    app_env: str = "development"

    # B2B API (US-005)
    # Pepper para el HMAC-SHA256 del secreto de las API keys. NUNCA en la BD.
    # En producción se carga desde Azure Key Vault.
    b2b_api_key_pepper: str = "dev-pepper-change-me-before-production"
    b2b_idempotency_window_hours: int = 24
    b2b_max_cards_per_query: int = 100


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
