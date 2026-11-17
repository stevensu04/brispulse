"""The live-only deployment: no database, schedule read straight from TransLink."""

import datetime as dt
import time
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from brispulse.config import MissingDatabaseError, Settings
from brispulse.gtfs_static.fetch import FetchError
from brispulse.gtfs_static.parse import GtfsFormatError
from brispulse.main import create_app
from brispulse.realtime.zip_reference import ZipReferenceHolder
from tests.gtfs_fixture import DEFAULT_FILES, build_zip_bytes
from tests.rt_fixture import alert, feed_bytes, trip_update, vehicle

SETTINGS = Settings(_env_file=None, translink_base_url="https://translink.test")
HEADERS = {"ETag": '"v1"', "Last-Modified": "Fri, 13 Nov 2026 19:45:24 GMT"}
PUBLISHED = dt.datetime(2026, 11, 13, 19, 45, 24, tzinfo=dt.UTC)


class FakeSchedule:
    """Serves a schedule zip and records the requests it receives."""

    def __init__(self, body: bytes | None = None, headers: dict[str, str] | None = None) -> None:
        self.body = build_zip_bytes() if body is None else body
        self.headers = HEADERS if headers is None else headers
        self.status = 200
        self.methods: list[str] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.methods.append(request.method)
        if self.status != 200:
            return httpx2.Response(self.status)
        content = b"" if request.method == "HEAD" else self.body
        return httpx2.Response(200, content=content, headers=self.headers)

    def holder(self) -> ZipReferenceHolder:
        client = httpx2.Client(transport=httpx2.MockTransport(self.handle))
        return ZipReferenceHolder(SETTINGS, client)


class TestConfiguration:
    def test_a_database_is_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("BRISPULSE_DATABASE_URL", raising=False)

        settings = Settings(_env_file=None)

        assert (settings.database_url, settings.live_only) == (None, True)

    def test_an_empty_variable_means_no_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "")

        assert Settings(_env_file=None).live_only is True

    def test_a_configured_database_turns_live_only_off(self) -> None:
        settings = Settings(_env_file=None, database_url="postgresql://u:p@host/db")

        assert settings.live_only is False
        assert settings.require_database_url() == "postgresql+psycopg://u:p@host/db"

    def test_commands_that_need_a_database_say_so(self) -> None:
        with pytest.raises(MissingDatabaseError, match="set DATABASE_URL"):
            SETTINGS.require_database_url()


class TestScheduleFromZip:
    def test_names_routes_stops_and_trips(self) -> None:
        holder = FakeSchedule().holder()

        assert holder.refresh() is True

        reference = holder.current
        assert reference is not None
        assert reference.routes["R1"] == ("100", "City Loop", "bus", "00FF00", "000000")
        assert reference.mode_of("R2") == "rail"
        assert reference.stops["ST1"].name == "Central Station"
        assert reference.trip_headsigns == {"T1": "City", "T2": "City", "T3": "Northside"}
        assert reference.published_at == PUBLISHED
        assert reference.feed_end_date == dt.date(2027, 1, 13)
        # Without a database the publication time identifies the version.
        assert reference.version_id == int(PUBLISHED.timestamp())
        assert holder.loaded_at is not None

    def test_the_large_stop_times_file_is_never_needed(self) -> None:
        schedule = FakeSchedule(build_zip_bytes({"stop_times.txt": None, "calendar.txt": None}))

        holder = schedule.holder()
        holder.refresh()

        assert holder.current is not None
        assert len(holder.current.trip_headsigns) == 3

    def test_trips_on_unknown_routes_are_left_out(self) -> None:
        trips = DEFAULT_FILES["trips.txt"] + "R404,WEEKDAY,T9,Nowhere,0,,\n"
        holder = FakeSchedule(build_zip_bytes({"trips.txt": trips})).holder()

        holder.refresh()

        assert holder.current is not None
        assert "T9" not in holder.current.trip_headsigns

    def test_an_unchanged_schedule_is_not_downloaded_again(self) -> None:
        schedule = FakeSchedule()
        holder = schedule.holder()
        holder.refresh()
        first = holder.current
        schedule.methods.clear()

        assert holder.refresh() is False
        assert schedule.methods == ["HEAD"]
        assert holder.current is first

    def test_a_newly_published_schedule_replaces_the_old_one(self) -> None:
        schedule = FakeSchedule()
        holder = schedule.holder()
        holder.refresh()
        schedule.body = build_zip_bytes(
            {"routes.txt": DEFAULT_FILES["routes.txt"] + "R3,300,Extra,,4,,,\n"}
        )
        schedule.headers = {"ETag": '"v2"', "Last-Modified": "Sat, 14 Nov 2026 19:45:24 GMT"}

        assert holder.refresh() is True
        assert holder.current is not None
        assert holder.current.mode_of("R3") == "ferry"
        assert holder.current.version_id == int(PUBLISHED.timestamp()) + 86_400

    def test_without_version_markers_the_content_identifies_the_version(self) -> None:
        holder = FakeSchedule(headers={}).holder()

        holder.refresh()

        assert holder.current is not None
        assert holder.current.published_at is None
        assert holder.current.version_id > 0

    @pytest.mark.parametrize(
        ("body", "error"),
        [
            (b"<html>Service unavailable</html>", GtfsFormatError),
            (build_zip_bytes({"routes.txt": None}), GtfsFormatError),
            (build_zip_bytes({"trips.txt": "route_id,service_id,trip_id\n"}), GtfsFormatError),
        ],
        ids=["not-a-zip", "missing-file", "no-trips"],
    )
    def test_an_unusable_download_is_refused(self, body: bytes, error: type[Exception]) -> None:
        holder = FakeSchedule(body).holder()

        with pytest.raises(error):
            holder.refresh()

        assert holder.current is None

    def test_a_failed_refresh_keeps_the_schedule_already_held(self) -> None:
        schedule = FakeSchedule()
        holder = schedule.holder()
        holder.refresh()
        held = holder.current
        schedule.status = 503

        with pytest.raises(FetchError):
            holder.refresh()

        assert holder.current is held


def test_the_whole_service_runs_with_no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start the real application in live-only mode against a fake TransLink.

    Everything is real except the network: the lifespan, the schedule download, the
    collector loop and the API. The feeds carry the current time, as live feeds do.
    """
    schedule = FakeSchedule()

    def translink(request: httpx2.Request) -> httpx2.Response:
        now = int(time.time())
        if request.url.path.endswith("SEQ_GTFS.zip"):
            return schedule.handle(request)
        feeds: dict[str, tuple[Any, ...]] = {
            "VehiclePositions": (vehicle("V1", trip_id="T1", timestamp=now - 5),),
            "TripUpdates": (
                trip_update("T1", start_date=time.strftime("%Y%m%d", time.gmtime(now - 86_400))),
            ),
            "Alerts": (alert("A1", periods=((now - 60, now + 3600),)),),
        }
        return httpx2.Response(
            200, content=feed_bytes(*feeds[request.url.path.rsplit("/", 1)[-1]], timestamp=now)
        )

    monkeypatch.setattr(
        "brispulse.realtime.zip_reference.fetch.make_client",
        lambda settings: httpx2.Client(transport=httpx2.MockTransport(translink)),
    )
    monkeypatch.setattr(
        "brispulse.runtime._make_client",
        lambda settings: httpx2.AsyncClient(transport=httpx2.MockTransport(translink)),
    )
    settings = Settings(
        _env_file=None,
        translink_base_url="https://translink.test",
        poll_vehicle_positions_seconds=0.2,
        poll_trip_updates_seconds=0.2,
        poll_alerts_seconds=0.2,
    )

    with TestClient(create_app(settings)) as client:
        states: set[str] = set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            feeds = client.get("/api/v1/status").json()["data"]["feeds"]
            states = {feed["state"] for feed in feeds.values()}
            if states == {"live"}:
                break
            time.sleep(0.05)
        assert states == {"live"}

        status = client.get("/api/v1/status").json()["data"]
        overview = client.get("/api/v1/overview").json()
        vehicles = client.get("/api/v1/vehicles").json()["data"]
        alerts = client.get("/api/v1/alerts").json()["data"]

    assert status["history_enabled"] is False
    assert status["static"]["routes"] == 2
    assert [v["vehicle_id"] for v in vehicles] == ["V1"]
    assert vehicles[0]["headsign"] == "City"
    assert vehicles[0]["predicted_delay_s"] == 120
    assert overview["data"]["trips"]["running"] == 1
    assert [a["alert_id"] for a in alerts] == ["A1"]
    assert overview["data"]["coverage"] is None
    assert (
        "coverage: not available, because this deployment keeps no history."
        in overview["meta"]["notes"]
    )
