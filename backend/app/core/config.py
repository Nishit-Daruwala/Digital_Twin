from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+psycopg://twin:twin@localhost:5433/twin"
    test_database_url: str = "postgresql+psycopg://twin:twin@localhost:5433/twin_test"

    jwt_secret: str = "dev-only-insecure-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14

    cors_origins: str = "http://localhost:3000"

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_extraction_model: str = "gpt-4o-mini"

    embedding_provider: str = "local"
    embedding_dim: int = 384

    app_env: str = "development"  # development / test / production

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        if self.app_env == "production":
            weak = {"", "change-me", "dev-only-insecure-secret"}
            if self.jwt_secret in weak or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a random string of 32+ chars in production")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS must list explicit origins in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
