"""Shared fixtures.

Tests marked ``db`` run against a real PostgreSQL database named ``brispulse_test``.
It is created on demand on the server started by ``docker compose up -d db`` and is
never the development database. In CI a missing database is an error; locally those
tests are skipped with a clear reason.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.db import make_engine, make_session_factory

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEST_URL = "postgresql+psycopg://brispulse:brispulse@localhost:5432/brispulse_test"


def _test_database_url() -> str:
    return os.environ.get("BRISPULSE_TEST_DATABASE_URL", DEFAULT_TEST_URL)


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    # "%" must be doubled: Alembic reads options through configparser interpolation.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logging"] = False
    return config


def _ensure_database_exists(database_url: str) -> None:
    url = make_url(database_url)
    if not (url.database or "").endswith("_test"):
        raise RuntimeError(f"refusing to run tests against non-test database {url.database!r}")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
            )
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _test_database_url()
    try:
        _ensure_database_exists(url)
    except OperationalError as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"PostgreSQL is not reachable (run `docker compose up -d db`): {exc}")
    return url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """An engine on a freshly migrated test database."""
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = make_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    yield make_session_factory(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE static_version, feed_fetch, trip_record, network_sample, "
                "alert_record, route_day_stats RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        translink_base_url="https://translink.test",
    )


@pytest.fixture
def anyio_backend() -> str:
    """Async tests run on asyncio, the loop the service uses."""
    return "asyncio"
