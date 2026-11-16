import pytest

from brispulse.config import Settings


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@host:5432/db",
        "postgresql://u:p@host:5432/db",
        "postgresql+psycopg://u:p@host:5432/db",
    ],
)
def test_database_url_always_selects_psycopg3(given: str) -> None:
    assert Settings(database_url=given).database_url == "postgresql+psycopg://u:p@host:5432/db"


def test_database_url_is_read_from_the_conventional_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BRISPULSE_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://u:p@host/db"


def test_static_feed_url_joins_base_and_path() -> None:
    settings = Settings(database_url="postgresql://x/y", translink_base_url="https://a.test/")

    assert settings.static_feed_url == "https://a.test/GTFS/SEQ_GTFS.zip"
