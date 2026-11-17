"""The static reference built straight from TransLink's zip, with no database.

This is what the live-only deployment uses (architecture §19). It reads only the three
small files needed to name things: routes, stops and trips. ``stop_times.txt``, the
4.67-million-row file, is never opened, so start-up stays quick and light. The price is
that nothing needing trip time spans is available: there is no real-time coverage.
"""

import datetime as dt
import logging
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx2

from brispulse.config import Settings
from brispulse.gtfs_static import fetch
from brispulse.gtfs_static.parse import (
    GtfsFormatError,
    read_feed_info,
    read_routes,
    read_stops,
    read_trip_headsigns,
)
from brispulse.realtime.reference import Reference, RouteInfo, StopInfo

logger = logging.getLogger(__name__)


def _version_id(remote: fetch.RemoteInfo, sha256: str) -> int:
    """A stable number for this copy of the schedule.

    With a database the version is a row ID. Without one, the publication time serves:
    it is what distinguishes one TransLink schedule file from the next.
    """
    if remote.last_modified is not None:
        return int(remote.last_modified.timestamp())
    return int(sha256[:8], 16)


def build_reference(zf: zipfile.ZipFile, source: fetch.Download) -> Reference:
    routes, _ = read_routes(zf)
    stops, _ = read_stops(zf)
    headsigns = read_trip_headsigns(zf, {route.route_id for route in routes})
    if not routes or not stops or not headsigns:
        raise GtfsFormatError("schedule has no routes, stops or trips")
    info = read_feed_info(zf)
    return Reference(
        version_id=_version_id(source.remote, source.sha256),
        routes={
            r.route_id: RouteInfo(r.short_name, r.long_name, r.mode, r.color, r.text_color)
            for r in routes
        },
        trip_headsigns={
            trip_id: sys.intern(headsign) if headsign else None
            for trip_id, headsign in headsigns.items()
        },
        stops={s.stop_id: StopInfo(s.name, s.lat, s.lon) for s in stops},
        published_at=source.remote.last_modified,
        feed_start_date=info.start_date,
        feed_end_date=info.end_date,
    )


class ZipReferenceHolder:
    """Holds the reference and reloads it when TransLink publishes a new schedule."""

    def __init__(self, settings: Settings, client: httpx2.Client | None = None) -> None:
        self._settings = settings
        self._client = client
        self._remote: fetch.RemoteInfo | None = None
        self.current: Reference | None = None
        self.loaded_at: dt.datetime | None = None

    def _unchanged(self, remote: fetch.RemoteInfo) -> bool:
        held = self._remote
        return (
            self.current is not None
            and held is not None
            and remote.etag is not None
            and remote.last_modified is not None
            and (remote.etag, remote.last_modified) == (held.etag, held.last_modified)
        )

    def refresh(self) -> bool:
        """Download and load the schedule if it differs from the one held. Blocking.

        Raises on failure and leaves the reference already held, if any, in place.
        """
        client = self._client or fetch.make_client(self._settings)
        try:
            url = self._settings.static_feed_url
            if self.current is not None and self._unchanged(fetch.head(client, url)):
                return False
            with tempfile.TemporaryDirectory(prefix="brispulse-gtfs-") as workdir:
                source = fetch.download(
                    client,
                    url,
                    Path(workdir) / "feed.zip",
                    self._settings.static_max_download_bytes,
                )
                if not zipfile.is_zipfile(source.path):
                    raise GtfsFormatError("downloaded file is not a zip archive")
                with zipfile.ZipFile(source.path) as zf:
                    reference = build_reference(zf, source)
        finally:
            if self._client is None:
                client.close()
        self.current = reference
        self._remote = source.remote
        self.loaded_at = dt.datetime.now(dt.UTC)
        logger.info(
            "loaded schedule from TransLink: %d routes, %d stops, %d trips",
            len(reference.routes),
            len(reference.stops),
            len(reference.trip_headsigns),
        )
        return True
