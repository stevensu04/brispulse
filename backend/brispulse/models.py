"""Database tables.

Reference data from the static GTFS feed is versioned: every row belongs to a
``static_version``, and exactly one version is active at a time. Real-time records
are interpreted against the active version (architecture §4.2).
"""

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit constraint names keep migrations deterministic across databases.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _version_fk() -> Mapped[int]:
    return mapped_column(
        ForeignKey("static_version.id", ondelete="CASCADE"),
        primary_key=True,
    )


class StaticVersion(Base):
    """One imported copy of TransLink's static GTFS zip."""

    __tablename__ = "static_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    feed_publisher: Mapped[str | None] = mapped_column(Text)
    feed_start_date: Mapped[dt.date | None] = mapped_column(Date)
    feed_end_date: Mapped[dt.date | None] = mapped_column(Date)
    route_count: Mapped[int] = mapped_column(Integer)
    stop_count: Mapped[int] = mapped_column(Integer)
    trip_count: Mapped[int] = mapped_column(Integer)
    stop_time_rows: Mapped[int] = mapped_column(Integer)
    # Rows read, accepted and rejected (with reasons) per file.
    report: Mapped[dict[str, Any]] = mapped_column(JSONB)
    imported_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    __table_args__ = (
        # The database itself guarantees that at most one version is active.
        Index(
            "uq_static_version_one_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class Route(Base):
    __tablename__ = "route"

    static_version_id: Mapped[int] = _version_fk()
    route_id: Mapped[str] = mapped_column(Text, primary_key=True)
    short_name: Mapped[str | None] = mapped_column(Text)
    long_name: Mapped[str | None] = mapped_column(Text)
    route_type: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    color: Mapped[str | None] = mapped_column(String(6))
    text_color: Mapped[str | None] = mapped_column(String(6))


class Stop(Base):
    __tablename__ = "stop"

    static_version_id: Mapped[int] = _version_fk()
    stop_id: Mapped[str] = mapped_column(Text, primary_key=True)
    code: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    location_type: Mapped[int] = mapped_column(SmallInteger)
    parent_station: Mapped[str | None] = mapped_column(Text)
    platform_code: Mapped[str | None] = mapped_column(Text)


class Trip(Base):
    """A scheduled trip, with its time span reduced from ``stop_times.txt``.

    Times are seconds after midnight of the GTFS service day and can exceed
    86,400 for trips that run past midnight.
    """

    __tablename__ = "trip"

    static_version_id: Mapped[int] = _version_fk()
    trip_id: Mapped[str] = mapped_column(Text, primary_key=True)
    route_id: Mapped[str] = mapped_column(Text)
    service_id: Mapped[str] = mapped_column(Text)
    headsign: Mapped[str | None] = mapped_column(Text)
    direction_id: Mapped[int | None] = mapped_column(SmallInteger)
    shape_id: Mapped[str | None] = mapped_column(Text)
    first_departure_s: Mapped[int] = mapped_column(Integer)
    last_arrival_s: Mapped[int] = mapped_column(Integer)
    stop_count: Mapped[int] = mapped_column(Integer)
    first_stop_id: Mapped[str] = mapped_column(Text)
    last_stop_id: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        Index("ix_trip_version_route", "static_version_id", "route_id"),
        Index("ix_trip_version_service", "static_version_id", "service_id"),
    )


class ServiceCalendar(Base):
    __tablename__ = "service_calendar"

    static_version_id: Mapped[int] = _version_fk()
    service_id: Mapped[str] = mapped_column(Text, primary_key=True)
    monday: Mapped[bool] = mapped_column(Boolean)
    tuesday: Mapped[bool] = mapped_column(Boolean)
    wednesday: Mapped[bool] = mapped_column(Boolean)
    thursday: Mapped[bool] = mapped_column(Boolean)
    friday: Mapped[bool] = mapped_column(Boolean)
    saturday: Mapped[bool] = mapped_column(Boolean)
    sunday: Mapped[bool] = mapped_column(Boolean)
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date] = mapped_column(Date)


class ServiceCalendarDate(Base):
    """An exception to the weekly calendar: 1 = service added, 2 = service removed."""

    __tablename__ = "service_calendar_date"

    static_version_id: Mapped[int] = _version_fk()
    service_id: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    exception_type: Mapped[int] = mapped_column(SmallInteger)


class FeedFetch(Base):
    """One attempt to fetch a real-time feed, successful or not (architecture §5.1).

    This is the record of what BrisPulse retrieved and when. Gaps in collection show
    up here as missing or failed rows; nothing is back-filled.
    """

    __tablename__ = "feed_fetch"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    feed: Mapped[str] = mapped_column(String(24))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(24))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    body_bytes: Mapped[int | None] = mapped_column(Integer)
    # The feed header's timestamp: when TransLink produced the data.
    source_timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    entity_count: Mapped[int | None] = mapped_column(Integer)
    accepted_count: Mapped[int | None] = mapped_column(Integer)
    # Reason -> number of entities rejected for it.
    rejected: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    anomaly: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    detail: Mapped[str | None] = mapped_column(Text)
    # Not a foreign key: the log outlives pruned static versions.
    static_version_id: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_feed_fetch_feed_fetched_at", "feed", "fetched_at"),)
