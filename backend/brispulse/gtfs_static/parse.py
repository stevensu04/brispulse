"""Read the static GTFS zip into validated rows.

Everything here is pure: it takes an open zip and returns rows plus a report of what
was read, accepted and rejected. Nothing is silently dropped; every rejected row is
counted under a reason.

``stop_times.txt`` (4.67 million rows for SEQ when measured on 2026-11-16) is never
loaded whole. It is streamed once and reduced to one time span per trip.
"""

import csv
import datetime as dt
import io
import zipfile
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# GTFS route_type codes observed in the SEQ feed: 0, 2, 3, 4.
_MODE_BY_ROUTE_TYPE = {0: "tram", 1: "metro", 2: "rail", 3: "bus", 4: "ferry"}


class GtfsFormatError(Exception):
    """The zip is not a usable GTFS feed (missing file, missing column)."""


@dataclass(frozen=True, slots=True)
class RouteRow:
    route_id: str
    short_name: str | None
    long_name: str | None
    route_type: int
    mode: str
    color: str | None
    text_color: str | None


@dataclass(frozen=True, slots=True)
class StopRow:
    stop_id: str
    code: str | None
    name: str
    lat: float
    lon: float
    location_type: int
    parent_station: str | None
    platform_code: str | None


@dataclass(frozen=True, slots=True)
class TripSpan:
    """What one trip's rows in ``stop_times.txt`` reduce to."""

    first_departure_s: int
    last_arrival_s: int
    stop_count: int
    first_stop_id: str
    last_stop_id: str


@dataclass(frozen=True, slots=True)
class TripRow:
    trip_id: str
    route_id: str
    service_id: str
    headsign: str | None
    direction_id: int | None
    shape_id: str | None
    first_departure_s: int
    last_arrival_s: int
    stop_count: int
    first_stop_id: str
    last_stop_id: str


@dataclass(frozen=True, slots=True)
class CalendarRow:
    service_id: str
    monday: bool
    tuesday: bool
    wednesday: bool
    thursday: bool
    friday: bool
    saturday: bool
    sunday: bool
    start_date: dt.date
    end_date: dt.date


@dataclass(frozen=True, slots=True)
class CalendarDateRow:
    service_id: str
    date: dt.date
    exception_type: int


@dataclass(frozen=True, slots=True)
class FeedInfo:
    publisher: str | None
    start_date: dt.date | None
    end_date: dt.date | None


@dataclass(slots=True)
class FileReport:
    rows_read: int = 0
    accepted: int = 0
    rejected: Counter[str] = field(default_factory=Counter)

    def reject(self, reason: str) -> None:
        self.rejected[reason] += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_read": self.rows_read,
            "accepted": self.accepted,
            "rejected": dict(self.rejected),
        }


@dataclass(slots=True)
class ParsedFeed:
    routes: list[RouteRow]
    stops: list[StopRow]
    trips: list[TripRow]
    calendars: list[CalendarRow]
    calendar_dates: list[CalendarDateRow]
    feed_info: FeedInfo
    files: dict[str, FileReport]
    # Trips whose service_id appears in neither calendar file. Kept, but counted:
    # such a trip can never be "scheduled today".
    trips_without_service: int

    def report(self) -> dict[str, Any]:
        return {
            "files": {name: rep.as_dict() for name, rep in self.files.items()},
            "trips_without_service": self.trips_without_service,
        }


def parse_gtfs_time(value: str) -> int:
    """Convert ``H:MM:SS`` to seconds after midnight of the service day.

    Hours may exceed 23: a trip that runs past midnight keeps counting (``25:10:00``).
    Raises ``ValueError`` for anything else.
    """
    hours, minutes, seconds = value.strip().split(":")
    h, m, s = int(hours), int(minutes), int(seconds)
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError(f"not a GTFS time: {value!r}")
    return h * 3600 + m * 60 + s


def parse_gtfs_date(value: str) -> dt.date:
    """Convert ``YYYYMMDD`` to a date. Raises ``ValueError`` otherwise."""
    value = value.strip()
    if len(value) != 8 or not value.isdigit():
        raise ValueError(f"not a GTFS date: {value!r}")
    return dt.date(int(value[:4]), int(value[4:6]), int(value[6:]))


def mode_for_route_type(route_type: int) -> str:
    return _MODE_BY_ROUTE_TYPE.get(route_type, "other")


def _text(value: str | None) -> str | None:
    """Empty and whitespace-only cells mean "no value"."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _open_csv(zf: zipfile.ZipFile, name: str) -> io.TextIOWrapper:
    try:
        raw = zf.open(name)
    except KeyError:
        raise GtfsFormatError(f"{name} is missing from the feed") from None
    # utf-8-sig: GTFS files commonly start with a byte-order mark.
    return io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")


def _dict_rows(zf: zipfile.ZipFile, name: str, required: set[str]) -> Iterator[dict[str, str]]:
    with _open_csv(zf, name) as handle:
        reader = csv.DictReader(handle)
        header = [column.strip() for column in reader.fieldnames or []]
        missing = required - set(header)
        if missing:
            raise GtfsFormatError(f"{name} lacks required column(s): {sorted(missing)}")
        reader.fieldnames = header
        yield from reader


def read_routes(zf: zipfile.ZipFile) -> tuple[list[RouteRow], FileReport]:
    report = FileReport()
    rows: dict[str, RouteRow] = {}
    for raw in _dict_rows(zf, "routes.txt", {"route_id", "route_type"}):
        report.rows_read += 1
        route_id = _text(raw["route_id"])
        if route_id is None:
            report.reject("missing_id")
            continue
        if route_id in rows:
            report.reject("duplicate_id")
            continue
        try:
            route_type = int(raw["route_type"])
        except ValueError:
            report.reject("bad_route_type")
            continue
        rows[route_id] = RouteRow(
            route_id=route_id,
            short_name=_text(raw.get("route_short_name")),
            long_name=_text(raw.get("route_long_name")),
            route_type=route_type,
            mode=mode_for_route_type(route_type),
            color=_hex_color(raw.get("route_color")),
            text_color=_hex_color(raw.get("route_text_color")),
        )
    report.accepted = len(rows)
    return list(rows.values()), report


def _hex_color(value: str | None) -> str | None:
    """A six-digit hex colour, upper-cased; anything else is treated as absent."""
    text = _text(value)
    if text is None or len(text) != 6:
        return None
    try:
        int(text, 16)
    except ValueError:
        return None
    return text.upper()


def read_stops(zf: zipfile.ZipFile) -> tuple[list[StopRow], FileReport]:
    report = FileReport()
    rows: dict[str, StopRow] = {}
    required = {"stop_id", "stop_name", "stop_lat", "stop_lon"}
    for raw in _dict_rows(zf, "stops.txt", required):
        report.rows_read += 1
        stop_id = _text(raw["stop_id"])
        if stop_id is None:
            report.reject("missing_id")
            continue
        if stop_id in rows:
            report.reject("duplicate_id")
            continue
        try:
            lat, lon = float(raw["stop_lat"]), float(raw["stop_lon"])
        except ValueError:
            report.reject("bad_coordinates")
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            report.reject("bad_coordinates")
            continue
        try:
            location_type = int(_text(raw.get("location_type")) or "0")
        except ValueError:
            report.reject("bad_location_type")
            continue
        rows[stop_id] = StopRow(
            stop_id=stop_id,
            code=_text(raw.get("stop_code")),
            name=_text(raw["stop_name"]) or stop_id,
            lat=lat,
            lon=lon,
            location_type=location_type,
            parent_station=_text(raw.get("parent_station")),
            platform_code=_text(raw.get("platform_code")),
        )
    report.accepted = len(rows)
    return list(rows.values()), report


def compute_trip_spans(zf: zipfile.ZipFile) -> tuple[dict[str, TripSpan], FileReport]:
    """Stream ``stop_times.txt`` once and keep one span per trip.

    A trip's span runs from its earliest to its latest listed time. Its first and last
    stops are those with the lowest and highest ``stop_sequence``. Rows are not assumed
    to be grouped by trip or ordered by sequence.
    """
    report = FileReport()
    # trip_id -> [start_s, end_s, stop_count, min_seq, first_stop_id, max_seq, last_stop_id]
    spans: dict[str, list[Any]] = {}
    with _open_csv(zf, "stop_times.txt") as handle:
        reader = csv.reader(handle)
        header = [column.strip() for column in next(reader, [])]
        required = ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"]
        missing = [column for column in required if column not in header]
        if missing:
            raise GtfsFormatError(f"stop_times.txt lacks required column(s): {missing}")
        i_trip, i_arr, i_dep, i_stop, i_seq = (header.index(column) for column in required)

        for row in reader:
            report.rows_read += 1
            try:
                trip_id, stop_id = row[i_trip], row[i_stop]
                sequence = int(row[i_seq])
                arrival_text, departure_text = row[i_arr], row[i_dep]
                # Either time may be blank at a stop that is not a timing point.
                arrival = parse_gtfs_time(arrival_text) if arrival_text.strip() else None
                departure = parse_gtfs_time(departure_text) if departure_text.strip() else None
            except (IndexError, ValueError):
                report.reject("bad_row")
                continue
            if not trip_id or not stop_id:
                report.reject("bad_row")
                continue

            earliest = arrival if arrival is not None else departure
            latest = departure if departure is not None else arrival
            span = spans.get(trip_id)
            if span is None:
                spans[trip_id] = [earliest, latest, 1, sequence, stop_id, sequence, stop_id]
            else:
                if earliest is not None and (span[0] is None or earliest < span[0]):
                    span[0] = earliest
                if latest is not None and (span[1] is None or latest > span[1]):
                    span[1] = latest
                span[2] += 1
                if sequence < span[3]:
                    span[3], span[4] = sequence, stop_id
                if sequence > span[5]:
                    span[5], span[6] = sequence, stop_id
            report.accepted += 1

    result = {
        trip_id: TripSpan(
            first_departure_s=span[0],
            last_arrival_s=span[1],
            stop_count=span[2],
            first_stop_id=span[4],
            last_stop_id=span[6],
        )
        for trip_id, span in spans.items()
        # A trip with no times at all has no usable span.
        if span[0] is not None and span[1] is not None
    }
    return result, report


def read_trips(
    zf: zipfile.ZipFile,
    route_ids: set[str],
    spans: dict[str, TripSpan],
) -> tuple[list[TripRow], FileReport]:
    report = FileReport()
    rows: dict[str, TripRow] = {}
    for raw in _dict_rows(zf, "trips.txt", {"trip_id", "route_id", "service_id"}):
        report.rows_read += 1
        trip_id = _text(raw["trip_id"])
        route_id = _text(raw["route_id"])
        service_id = _text(raw["service_id"])
        if trip_id is None or route_id is None or service_id is None:
            report.reject("missing_id")
            continue
        if trip_id in rows:
            report.reject("duplicate_id")
            continue
        if route_id not in route_ids:
            report.reject("unknown_route")
            continue
        span = spans.get(trip_id)
        if span is None:
            report.reject("no_stop_times")
            continue
        direction_text = _text(raw.get("direction_id"))
        try:
            direction_id = int(direction_text) if direction_text is not None else None
        except ValueError:
            report.reject("bad_direction")
            continue
        rows[trip_id] = TripRow(
            trip_id=trip_id,
            route_id=route_id,
            service_id=service_id,
            headsign=_text(raw.get("trip_headsign")),
            direction_id=direction_id,
            shape_id=_text(raw.get("shape_id")),
            first_departure_s=span.first_departure_s,
            last_arrival_s=span.last_arrival_s,
            stop_count=span.stop_count,
            first_stop_id=span.first_stop_id,
            last_stop_id=span.last_stop_id,
        )
    report.accepted = len(rows)
    return list(rows.values()), report


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def read_calendar(zf: zipfile.ZipFile) -> tuple[list[CalendarRow], FileReport]:
    report = FileReport()
    if "calendar.txt" not in zf.namelist():
        # Optional in GTFS when calendar_dates.txt lists every service day.
        return [], report
    rows: dict[str, CalendarRow] = {}
    required = {"service_id", "start_date", "end_date", *_WEEKDAYS}
    for raw in _dict_rows(zf, "calendar.txt", required):
        report.rows_read += 1
        service_id = _text(raw["service_id"])
        if service_id is None:
            report.reject("missing_id")
            continue
        if service_id in rows:
            report.reject("duplicate_id")
            continue
        days = [raw[day].strip() for day in _WEEKDAYS]
        if any(day not in ("0", "1") for day in days):
            report.reject("bad_weekday_flag")
            continue
        try:
            start, end = parse_gtfs_date(raw["start_date"]), parse_gtfs_date(raw["end_date"])
        except ValueError:
            report.reject("bad_date")
            continue
        monday, tuesday, wednesday, thursday, friday, saturday, sunday = (
            day == "1" for day in days
        )
        rows[service_id] = CalendarRow(
            service_id=service_id,
            monday=monday,
            tuesday=tuesday,
            wednesday=wednesday,
            thursday=thursday,
            friday=friday,
            saturday=saturday,
            sunday=sunday,
            start_date=start,
            end_date=end,
        )
    report.accepted = len(rows)
    return list(rows.values()), report


def read_calendar_dates(zf: zipfile.ZipFile) -> tuple[list[CalendarDateRow], FileReport]:
    report = FileReport()
    if "calendar_dates.txt" not in zf.namelist():
        return [], report
    rows: dict[tuple[str, dt.date], CalendarDateRow] = {}
    required = {"service_id", "date", "exception_type"}
    for raw in _dict_rows(zf, "calendar_dates.txt", required):
        report.rows_read += 1
        service_id = _text(raw["service_id"])
        if service_id is None:
            report.reject("missing_id")
            continue
        try:
            date = parse_gtfs_date(raw["date"])
        except ValueError:
            report.reject("bad_date")
            continue
        exception_type = raw["exception_type"].strip()
        if exception_type not in ("1", "2"):
            report.reject("bad_exception_type")
            continue
        if (service_id, date) in rows:
            report.reject("duplicate_id")
            continue
        rows[(service_id, date)] = CalendarDateRow(service_id, date, int(exception_type))
    report.accepted = len(rows)
    return list(rows.values()), report


def read_feed_info(zf: zipfile.ZipFile) -> FeedInfo:
    """Feed metadata. Optional in GTFS, so every field may be absent."""
    if "feed_info.txt" not in zf.namelist():
        return FeedInfo(None, None, None)
    first = next(_dict_rows(zf, "feed_info.txt", set()), None)
    if first is None:
        return FeedInfo(None, None, None)

    def date_or_none(column: str) -> dt.date | None:
        text = _text(first.get(column))
        if text is None:
            return None
        try:
            return parse_gtfs_date(text)
        except ValueError:
            return None

    return FeedInfo(
        publisher=_text(first.get("feed_publisher_name")),
        start_date=date_or_none("feed_start_date"),
        end_date=date_or_none("feed_end_date"),
    )


def parse_feed(zf: zipfile.ZipFile) -> ParsedFeed:
    routes, routes_report = read_routes(zf)
    stops, stops_report = read_stops(zf)
    spans, stop_times_report = compute_trip_spans(zf)
    trips, trips_report = read_trips(zf, {route.route_id for route in routes}, spans)
    calendars, calendar_report = read_calendar(zf)
    calendar_dates, calendar_dates_report = read_calendar_dates(zf)

    known_services = {row.service_id for row in calendars}
    known_services.update(row.service_id for row in calendar_dates)
    trips_without_service = sum(1 for trip in trips if trip.service_id not in known_services)

    return ParsedFeed(
        routes=routes,
        stops=stops,
        trips=trips,
        calendars=calendars,
        calendar_dates=calendar_dates,
        feed_info=read_feed_info(zf),
        files={
            "routes.txt": routes_report,
            "stops.txt": stops_report,
            "stop_times.txt": stop_times_report,
            "trips.txt": trips_report,
            "calendar.txt": calendar_report,
            "calendar_dates.txt": calendar_dates_report,
        },
        trips_without_service=trips_without_service,
    )
