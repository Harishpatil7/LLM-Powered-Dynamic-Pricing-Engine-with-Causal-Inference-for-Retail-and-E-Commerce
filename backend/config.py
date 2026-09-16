from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration loaded from a local .env file when present."""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    environment: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/app.db"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    # Replace this value before deploying. It intentionally lets the local
    # development workspace run without asking students to generate a secret.
    auth_secret_key: str = "local-development-only-change-before-deployment"
    auth_token_ttl_hours: int = 24


settings = Settings()
