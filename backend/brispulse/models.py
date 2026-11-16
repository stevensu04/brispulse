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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
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
    # none_as_null: a fetch with nothing to report stores SQL NULL, not the JSON value null.
    rejected: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    anomaly: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    detail: Mapped[str | None] = mapped_column(Text)
    # Not a foreign key: the log outlives pruned static versions.
    static_version_id: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_feed_fetch_feed_fetched_at", "feed", "fetched_at"),)


class TripRecord(Base):
    """One trip on one service day, summarised from its observations while running.

    Each observation is TransLink's predicted delay at the trip's next stop, taken when
    the trip-updates feed was fetched. The unit of analysis for route statistics is the
    trip, not the observation: a long trip is sampled many more times than a short one,
    and counting observations would let it dominate (architecture §2.3, §6.2).
    """

    __tablename__ = "trip_record"

    service_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    trip_id: Mapped[str] = mapped_column(Text, primary_key=True)
    route_id: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str | None] = mapped_column(String(16))
    relationship: Mapped[str] = mapped_column(String(24))
    vehicle_id: Mapped[str | None] = mapped_column(Text)
    static_version_id: Mapped[int] = mapped_column(Integer)
    first_obs_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    last_obs_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    # Observations that carried a plausible delay; the figures below summarise these.
    obs_count: Mapped[int] = mapped_column(Integer)
    delay_median_s: Mapped[int | None] = mapped_column(Integer)
    delay_min_s: Mapped[int | None] = mapped_column(Integer)
    delay_max_s: Mapped[int | None] = mapped_column(Integer)
    delay_last_s: Mapped[int | None] = mapped_column(Integer)
    early_obs_count: Mapped[int] = mapped_column(Integer)
    late_obs_count: Mapped[int] = mapped_column(Integer)
    # Observations left out: delay beyond the plausible range, or no delay given.
    implausible_count: Mapped[int] = mapped_column(Integer)
    without_delay_count: Mapped[int] = mapped_column(Integer)
    # False while the trip is still being observed.
    completed: Mapped[bool] = mapped_column(Boolean)
    # Raw delays, kept only while the trip is in flight so a restart can resume it.
    samples: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))

    __table_args__ = (
        Index("ix_trip_record_date_route", "service_date", "route_id"),
        Index(
            "ix_trip_record_in_flight",
            "completed",
            postgresql_where=text("NOT completed"),
        ),
    )


class NetworkSample(Base):
    """The state of the network at one moment, taken every five minutes (architecture §4.3).

    One row per mode plus an ``all`` row. A metric is NULL when the feed it depends on
    was not usable at that moment: the gap is recorded as a gap, never as zero.
    """

    __tablename__ = "network_sample"

    sampled_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), primary_key=True)
    static_version_id: Mapped[int | None] = mapped_column(Integer)
    vehicle_positions_state: Mapped[str] = mapped_column(String(16))
    trip_updates_state: Mapped[str] = mapped_column(String(16))
    alerts_state: Mapped[str] = mapped_column(String(16))
    vehicles_fresh: Mapped[int | None] = mapped_column(Integer)
    vehicles_last_seen: Mapped[int | None] = mapped_column(Integer)
    trips_running: Mapped[int | None] = mapped_column(Integer)
    # Real-time coverage: scheduled trips in progress, and how many had live data.
    trips_scheduled: Mapped[int | None] = mapped_column(Integer)
    trips_with_update: Mapped[int | None] = mapped_column(Integer)
    trips_with_vehicle: Mapped[int | None] = mapped_column(Integer)
    delay_sample_size: Mapped[int | None] = mapped_column(Integer)
    delay_median_s: Mapped[int | None] = mapped_column(Integer)
    delay_p90_s: Mapped[int | None] = mapped_column(Integer)
    delay_early: Mapped[int | None] = mapped_column(Integer)
    delay_within_band: Mapped[int | None] = mapped_column(Integer)
    delay_late: Mapped[int | None] = mapped_column(Integer)
    delay_excluded_implausible: Mapped[int | None] = mapped_column(Integer)
    # Alerts are network-wide: filled on the ``all`` row only.
    alerts_active: Mapped[int | None] = mapped_column(Integer)
    alerts_active_planned_works: Mapped[int | None] = mapped_column(Integer)


class AlertRecord(Base):
    """A service alert as it appeared in the feed, and for how long.

    The key includes a hash of the content, so an alert whose text or periods change
    gets a new row and the earlier wording is preserved.
    """

    __tablename__ = "alert_record"

    alert_id: Mapped[str] = mapped_column(Text, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(40), primary_key=True)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    cause: Mapped[str] = mapped_column(String(32))
    effect: Mapped[str] = mapped_column(String(32))
    header: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    active_periods: Mapped[list[Any]] = mapped_column(JSONB)
    route_ids: Mapped[list[Any]] = mapped_column(JSONB)
    stop_ids: Mapped[list[Any]] = mapped_column(JSONB)

    __table_args__ = (Index("ix_alert_record_last_seen", "last_seen_at"),)


class RouteDayStats(Base):
    """One route on one finished service day, rolled up from ``trip_record``.

    Percentiles are taken across trips (each trip contributes its median delay) and are
    NULL when too few trips were observed.
    """

    __tablename__ = "route_day_stats"

    service_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    route_id: Mapped[str] = mapped_column(Text, primary_key=True)
    mode: Mapped[str | None] = mapped_column(String(16))
    # Trips with enough observations to count.
    trips_observed: Mapped[int] = mapped_column(Integer)
    # From the static schedule; NULL if it could not be determined for that date.
    trips_scheduled: Mapped[int | None] = mapped_column(Integer)
    delay_p50_s: Mapped[int | None] = mapped_column(Integer)
    delay_p90_s: Mapped[int | None] = mapped_column(Integer)
    trips_early: Mapped[int] = mapped_column(Integer)
    trips_within_band: Mapped[int] = mapped_column(Integer)
    trips_late: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
