from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    slack_bot_token: SecretStr
    slack_signing_secret: SecretStr

    xai_api_key: SecretStr
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model: str = "grok-2-latest"

    backend_base_url: str = "http://localhost:8080"

    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    grok_max_tool_rounds: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
