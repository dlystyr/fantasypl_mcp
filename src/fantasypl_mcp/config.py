"""Configuration management using Pydantic settings."""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL settings
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="fantasypl", alias="POSTGRES_DB")

    # Valkey settings (Redis-compatible)
    valkey_host: str = Field(default="localhost", alias="VALKEY_HOST")
    valkey_port: int = Field(default=6379, alias="VALKEY_PORT")
    valkey_password: str | None = Field(default=None, alias="VALKEY_PASSWORD")
    valkey_db: int = Field(default=0, alias="VALKEY_DB")

    # Server settings
    server_host: str = Field(default="0.0.0.0", alias="SERVER_HOST")
    server_port: int = Field(default=8000, alias="SERVER_PORT")

    # FPL API settings
    fpl_api_base_url: str = Field(
        default="https://fantasy.premierleague.com/api",
        alias="FPL_API_BASE_URL"
    )

    # Cache TTL settings (in seconds)
    cache_ttl_bootstrap: int = Field(default=3600, alias="CACHE_TTL_BOOTSTRAP")
    cache_ttl_player: int = Field(default=1800, alias="CACHE_TTL_PLAYER")
    cache_ttl_fixtures: int = Field(default=3600, alias="CACHE_TTL_FIXTURES")

    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def valkey_url(self) -> str:
        """Get Valkey connection URL (uses redis:// protocol as Valkey is Redis-compatible)."""
        if self.valkey_password:
            return f"redis://:{self.valkey_password}@{self.valkey_host}:{self.valkey_port}/{self.valkey_db}"
        return f"redis://{self.valkey_host}:{self.valkey_port}/{self.valkey_db}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
