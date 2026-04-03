"""Application configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # App
    app_name: str = "LLM Monitor"
    app_version: str = "0.1.0"
    debug: bool = False

    # API
    api_prefix: str = "/api/v1"

    # CORS
    cors_origins: list[str] = ["*"]

    # Elasticsearch
    elasticsearch_url: str = "http://10.1.246.236:9200"

    # Metrics collection
    collection_interval: int = 10  # seconds

    # Data retention
    retention_days: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
