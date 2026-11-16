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

    realtime_path: str = "/api/realtime/SEQ"
    # TransLink refreshes its feeds every 10-30 s (measured 2026-11-16). Polling faster
    # than that returns nothing new. Defaults are the approved starting values.
    poll_vehicle_positions_seconds: float = 30.0
    poll_trip_updates_seconds: float = 60.0
    poll_alerts_seconds: float = 120.0
    realtime_timeout_seconds: float = 10.0
    # Turn off to run the HTTP application without contacting TransLink.
    collector_enabled: bool = True

    # History (architecture §4.3): turn off to collect without storing anything.
    history_enabled: bool = True
    history_sample_interval_seconds: float = 300.0
    history_maintenance_seconds: float = 3600.0
    # Rows older than this are deleted. Trip records go only once their day is rolled up.
    feed_fetch_retention_days: int = 30
    trip_record_retention_days: int = 35

    # How often to ask whether TransLink has published a new static schedule.
    static_check_interval_seconds: float = 6 * 3600.0
    # GTFS times are local to the agency (agency.txt: Australia/Brisbane).
    service_timezone: str = "Australia/Brisbane"

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
