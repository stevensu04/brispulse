"""Builds small GTFS zips for tests.

The default feed is synthetic: two routes, three stops, three trips. One trip runs past
midnight. Tests override individual files to exercise failure cases.
"""

import io
import zipfile
from pathlib import Path

DEFAULT_FILES: dict[str, str] = {
    "feed_info.txt": (
        "feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,feed_end_date\n"
        "Test Publisher,https://example.test/,en,20261114,20270113\n"
    ),
    "routes.txt": (
        "route_id,route_short_name,route_long_name,route_desc,route_type,route_url,"
        "route_color,route_text_color\n"
        "R1,100,City Loop,,3,,00ff00,000000\n"
        "R2,BNSH,Northern Line,,2,,,\n"
    ),
    "stops.txt": (
        "stop_id,stop_code,stop_name,stop_desc,stop_lat,stop_lon,zone_id,stop_url,"
        "location_type,parent_station,platform_code\n"
        "S1,001,First Street,,-27.47,153.02,1,,0,,\n"
        "S2,002,Second Street,,-27.48,153.03,1,,0,,\n"
        "ST1,,Central Station,,-27.46,153.02,1,,1,,\n"
    ),
    "trips.txt": (
        "route_id,service_id,trip_id,trip_headsign,direction_id,block_id,shape_id\n"
        "R1,WEEKDAY,T1,City,0,,SH1\n"
        "R1,WEEKDAY,T2,City,1,,SH1\n"
        "R2,SATURDAY,T3,Northside,,,\n"
    ),
    "stop_times.txt": (
        "trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type\n"
        "T1,08:00:00,08:00:00,S1,1,0,0\n"
        "T1,08:10:00,08:11:00,S2,2,0,0\n"
        # T2: listed out of order and running past midnight.
        "T2,24:30:00,24:30:00,S1,2,0,0\n"
        "T2,23:50:00,23:50:00,S2,1,0,0\n"
        # T3: the middle stop is not a timing point.
        "T3,09:00:00,09:00:00,S1,1,0,0\n"
        "T3,,,ST1,2,0,0\n"
        "T3,09:20:00,09:25:00,S2,3,0,0\n"
    ),
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\n"
        "WEEKDAY,1,1,1,1,1,0,0,20261114,20270113\n"
        "SATURDAY,0,0,0,0,0,1,0,20261114,20270113\n"
    ),
    "calendar_dates.txt": (
        "service_id,date,exception_type\nWEEKDAY,20261225,2\nSATURDAY,20261225,1\n"
    ),
}


def build_zip_bytes(overrides: dict[str, str | None] | None = None) -> bytes:
    """Return a GTFS zip. ``overrides`` replaces a file's text, or removes it with None."""
    files: dict[str, str | None] = {**DEFAULT_FILES, **(overrides or {})}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files.items():
            if text is not None:
                zf.writestr(name, text)
    return buffer.getvalue()


def open_zip(overrides: dict[str, str | None] | None = None) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(build_zip_bytes(overrides)))


def write_zip(path: Path, overrides: dict[str, str | None] | None = None) -> Path:
    path.write_bytes(build_zip_bytes(overrides))
    return path
