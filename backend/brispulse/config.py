"""Application settings, read from environment variables (and a local ``.env`` file)."""

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BRISPULSE_",
        # Commands run from backend/, the .env file lives at the repository root.
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    # Hosting platforms conventionally provide DATABASE_URL without a prefix.
    database_url: str = Field(
        validation_alias=AliasChoices("BRISPULSE_DATABASE_URL", "DATABASE_URL"),
    )

    translink_base_url: str = "https://gtfsrt.api.translink.com.au"
    static_feed_path: str = "/GTFS/SEQ_GTFS.zip"
    # Identifies this client to TransLink and says where to find its operator.
    user_agent: str = "BrisPulse/0.1 (+https://github.com/stevensu04/brispulse)"

    static_download_timeout_seconds: float = 300.0
    # The SEQ zip was 43 MB when measured (2026-11-16). Anything far larger is not that file.
    static_max_download_bytes: int = 500 * 1024 * 1024

    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3_driver(cls, value: str) -> str:
        """Accept the URL forms hosts hand out and select the psycopg 3 driver."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def static_feed_url(self) -> str:
        return self.translink_base_url.rstrip("/") + self.static_feed_path


@lru_cache
def get_settings() -> Settings:
    # Values come from the environment; a missing DATABASE_URL fails here, at start-up.
    return Settings()
