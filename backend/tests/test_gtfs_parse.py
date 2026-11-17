import datetime as dt

import pytest

from brispulse.gtfs_static.parse import (
    GtfsFormatError,
    compute_trip_spans,
    mode_for_route_type,
    parse_feed,
    parse_gtfs_date,
    parse_gtfs_time,
    read_calendar,
    read_calendar_dates,
    read_feed_info,
    read_routes,
    read_stops,
)
from tests.gtfs_fixture import DEFAULT_FILES, open_zip


class TestParseGtfsTime:
    @pytest.mark.parametrize(
        ("text", "seconds"),
        [
            ("00:00:00", 0),
            ("08:41:50", 31_310),
            ("8:05:00", 29_100),
            ("23:59:59", 86_399),
            # Past midnight: the latest SEQ trip ended at 30:33 when measured.
            ("24:30:00", 88_200),
            ("30:33:00", 109_980),
            (" 09:00:00 ", 32_400),
        ],
    )
    def test_valid_times(self, text: str, seconds: int) -> None:
        assert parse_gtfs_time(text) == seconds

    @pytest.mark.parametrize(
        "text", ["", "0800", "08:00", "08:60:00", "08:00:60", "-1:00:00", "a:b:c"]
    )
    def test_invalid_times_raise(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_gtfs_time(text)


class TestParseGtfsDate:
    def test_valid_date(self) -> None:
        assert parse_gtfs_date("20261116") == dt.date(2026, 11, 16)

    @pytest.mark.parametrize("text", ["", "2026-11-16", "2026111", "20261332", "abcdefgh"])
    def test_invalid_dates_raise(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_gtfs_date(text)


@pytest.mark.parametrize(
    ("route_type", "mode"),
    [(0, "tram"), (2, "rail"), (3, "bus"), (4, "ferry"), (712, "other")],
)
def test_mode_for_route_type(route_type: int, mode: str) -> None:
    assert mode_for_route_type(route_type) == mode


class TestReadRoutes:
    def test_reads_routes_and_derives_mode(self) -> None:
        routes, report = read_routes(open_zip())

        by_id = {route.route_id: route for route in routes}
        assert by_id["R1"].mode == "bus"
        assert by_id["R1"].short_name == "100"
        assert by_id["R1"].color == "00FF00"
        assert by_id["R2"].mode == "rail"
        assert by_id["R2"].color is None
        assert (report.rows_read, report.accepted) == (2, 2)

    def test_handles_a_byte_order_mark_and_padded_headers(self) -> None:
        text = "﻿route_id , route_type\nR1,3\n"

        routes, _ = read_routes(open_zip({"routes.txt": text}))

        assert [route.route_id for route in routes] == ["R1"]

    def test_counts_rejected_rows_by_reason(self) -> None:
        text = "route_id,route_type\nR1,3\nR1,3\n,3\nR9,bus\n"

        routes, report = read_routes(open_zip({"routes.txt": text}))

        assert [route.route_id for route in routes] == ["R1"]
        assert report.rows_read == 4
        assert dict(report.rejected) == {"duplicate_id": 1, "missing_id": 1, "bad_route_type": 1}

    def test_missing_file_is_a_format_error(self) -> None:
        with pytest.raises(GtfsFormatError, match=r"routes\.txt is missing"):
            read_routes(open_zip({"routes.txt": None}))

    def test_missing_column_is_a_format_error(self) -> None:
        with pytest.raises(GtfsFormatError, match="route_type"):
            read_routes(open_zip({"routes.txt": "route_id\nR1\n"}))


class TestReadStops:
    def test_reads_stops_and_stations(self) -> None:
        stops, report = read_stops(open_zip())

        by_id = {stop.stop_id: stop for stop in stops}
        assert by_id["S1"].lat == pytest.approx(-27.47)
        assert by_id["S1"].code == "001"
        assert by_id["ST1"].location_type == 1
        assert by_id["ST1"].code is None
        assert report.accepted == 3

    def test_rejects_unusable_coordinates(self) -> None:
        text = (
            "stop_id,stop_name,stop_lat,stop_lon\n"
            "OK,Fine,-27.5,153.0\n"
            "BLANK,No position,,\n"
            "FAR,Off the planet,-127.5,153.0\n"
        )

        stops, report = read_stops(open_zip({"stops.txt": text}))

        assert [stop.stop_id for stop in stops] == ["OK"]
        assert dict(report.rejected) == {"bad_coordinates": 2}


class TestComputeTripSpans:
    def test_span_covers_first_to_last_time(self) -> None:
        spans, report = compute_trip_spans(open_zip())

        assert spans["T1"].first_departure_s == 8 * 3600
        assert spans["T1"].last_arrival_s == 8 * 3600 + 11 * 60
        assert spans["T1"].stop_count == 2
        assert (spans["T1"].first_stop_id, spans["T1"].last_stop_id) == ("S1", "S2")
        assert (report.rows_read, report.accepted) == (7, 7)

    def test_rows_out_of_order_and_past_midnight(self) -> None:
        spans, _ = compute_trip_spans(open_zip())

        assert spans["T2"].first_departure_s == 23 * 3600 + 50 * 60
        assert spans["T2"].last_arrival_s == 24 * 3600 + 30 * 60
        # First and last stop follow stop_sequence, not file order.
        assert (spans["T2"].first_stop_id, spans["T2"].last_stop_id) == ("S2", "S1")

    def test_blank_times_at_non_timing_points_are_allowed(self) -> None:
        spans, report = compute_trip_spans(open_zip())

        assert spans["T3"].stop_count == 3
        assert spans["T3"].first_departure_s == 9 * 3600
        assert spans["T3"].last_arrival_s == 9 * 3600 + 25 * 60
        assert not report.rejected

    def test_malformed_rows_are_rejected_not_fatal(self) -> None:
        text = (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "T1,08:00:00,08:00:00,S1,1\n"
            "T1,late,08:10:00,S2,2\n"
            "T1,08:20:00,08:20:00,S2,third\n"
            "T1,08:30:00\n"
        )

        spans, report = compute_trip_spans(open_zip({"stop_times.txt": text}))

        assert spans["T1"].stop_count == 1
        assert report.rows_read == 4
        assert dict(report.rejected) == {"bad_row": 3}

    def test_trip_without_any_time_has_no_span(self) -> None:
        text = "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT1,,,S1,1\n"

        spans, _ = compute_trip_spans(open_zip({"stop_times.txt": text}))

        assert spans == {}


class TestCalendars:
    def test_reads_weekly_calendar(self) -> None:
        calendars, _ = read_calendar(open_zip())

        weekday = next(row for row in calendars if row.service_id == "WEEKDAY")
        assert (weekday.monday, weekday.friday, weekday.saturday) == (True, True, False)
        assert weekday.start_date == dt.date(2026, 11, 14)
        assert weekday.end_date == dt.date(2027, 1, 13)

    def test_rejects_bad_calendar_rows(self) -> None:
        header = DEFAULT_FILES["calendar.txt"].splitlines()[0]
        text = f"{header}\nBAD,1,1,1,1,1,x,0,20261114,20270113\nWORSE,1,1,1,1,1,0,0,soon,20270113\n"

        calendars, report = read_calendar(open_zip({"calendar.txt": text}))

        assert calendars == []
        assert dict(report.rejected) == {"bad_weekday_flag": 1, "bad_date": 1}

    def test_reads_exceptions(self) -> None:
        dates, _ = read_calendar_dates(open_zip())

        assert {(row.service_id, row.date, row.exception_type) for row in dates} == {
            ("WEEKDAY", dt.date(2026, 12, 25), 2),
            ("SATURDAY", dt.date(2026, 12, 25), 1),
        }

    def test_rejects_unknown_exception_type(self) -> None:
        text = "service_id,date,exception_type\nWEEKDAY,20261225,3\n"

        dates, report = read_calendar_dates(open_zip({"calendar_dates.txt": text}))

        assert dates == []
        assert dict(report.rejected) == {"bad_exception_type": 1}

    def test_calendar_files_are_optional(self) -> None:
        zf = open_zip({"calendar.txt": None, "calendar_dates.txt": None})

        assert read_calendar(zf)[0] == []
        assert read_calendar_dates(zf)[0] == []


class TestFeedInfo:
    def test_reads_publisher_and_validity_window(self) -> None:
        info = read_feed_info(open_zip())

        assert info.publisher == "Test Publisher"
        assert (info.start_date, info.end_date) == (dt.date(2026, 11, 14), dt.date(2027, 1, 13))

    def test_absent_file_yields_empty_info(self) -> None:
        info = read_feed_info(open_zip({"feed_info.txt": None}))

        assert (info.publisher, info.start_date, info.end_date) == (None, None, None)


class TestParseFeed:
    def test_joins_trips_to_routes_and_spans(self) -> None:
        feed = parse_feed(open_zip())

        by_id = {trip.trip_id: trip for trip in feed.trips}
        assert set(by_id) == {"T1", "T2", "T3"}
        assert by_id["T1"].route_id == "R1"
        assert by_id["T1"].direction_id == 0
        assert by_id["T3"].direction_id is None
        assert by_id["T3"].shape_id is None
        assert by_id["T2"].last_arrival_s == 88_200
        assert feed.trips_without_service == 0

    def test_trips_with_unknown_route_or_no_stop_times_are_rejected(self) -> None:
        trips = (
            DEFAULT_FILES["trips.txt"] + "R404,WEEKDAY,T4,Nowhere,0,,\nR1,WEEKDAY,T5,Ghost,0,,\n"
        )
        stop_times = DEFAULT_FILES["stop_times.txt"] + "T4,10:00:00,10:00:00,S1,1,0,0\n"

        feed = parse_feed(open_zip({"trips.txt": trips, "stop_times.txt": stop_times}))

        assert {trip.trip_id for trip in feed.trips} == {"T1", "T2", "T3"}
        assert dict(feed.files["trips.txt"].rejected) == {"unknown_route": 1, "no_stop_times": 1}

    def test_counts_trips_whose_service_is_undefined(self) -> None:
        trips = DEFAULT_FILES["trips.txt"] + "R1,HOLIDAY,T6,City,0,,\n"
        stop_times = DEFAULT_FILES["stop_times.txt"] + "T6,10:00:00,10:00:00,S1,1,0,0\n"

        feed = parse_feed(open_zip({"trips.txt": trips, "stop_times.txt": stop_times}))

        assert "T6" in {trip.trip_id for trip in feed.trips}
        assert feed.trips_without_service == 1

    def test_report_is_json_serialisable_summary(self) -> None:
        report = parse_feed(open_zip()).report()

        assert report["files"]["stop_times.txt"] == {"rows_read": 7, "accepted": 7, "rejected": {}}
        assert report["files"]["trips.txt"]["accepted"] == 3
        assert report["trips_without_service"] == 0
