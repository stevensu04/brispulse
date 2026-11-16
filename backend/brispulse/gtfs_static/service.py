"""Check for, download and import a new static GTFS version."""

import enum
import logging
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx2
from sqlalchemy.orm import Session, sessionmaker

from brispulse.config import Settings
from brispulse.gtfs_static import fetch, loader
from brispulse.gtfs_static.parse import GtfsFormatError, parse_feed
from brispulse.models import StaticVersion

logger = logging.getLogger(__name__)


class Outcome(enum.StrEnum):
    IMPORTED = "imported"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class ImportResult:
    outcome: Outcome
    version_id: int | None
    detail: str


def _same_remote(active: StaticVersion, remote: fetch.RemoteInfo) -> bool:
    """True when the server's version markers match the active version.

    Both markers must be present and equal. A missing marker means "cannot tell", which
    falls through to a download and a content-hash comparison.
    """
    return (
        remote.etag is not None
        and remote.last_modified is not None
        and remote.etag == active.etag
        and remote.last_modified == active.last_modified
    )


def remote_has_changed(
    client: httpx2.Client,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> bool:
    """Cheap check (one HEAD request): has TransLink published a different file?"""
    with session_factory() as session:
        active = loader.get_active_version(session)
    if active is None:
        return True
    return not _same_remote(active, fetch.head(client, settings.static_feed_url))


def run_import(
    settings: Settings,
    session_factory: sessionmaker[Session],
    *,
    client: httpx2.Client | None = None,
    local_file: Path | None = None,
    force: bool = False,
) -> ImportResult:
    """Import the static feed if it differs from the active version.

    ``local_file`` imports a zip from disk instead of downloading. ``force`` re-imports
    an identical file and overrides the shrink guard.
    """
    with tempfile.TemporaryDirectory(prefix="brispulse-gtfs-") as workdir:
        if local_file is not None:
            source = fetch.describe_local_file(local_file)
            # Record the file name only: the full path would expose a local directory layout.
            source_url = f"file:{local_file.name}"
        else:
            owns_client = client is None
            http = client or fetch.make_client(settings)
            try:
                if not force and not remote_has_changed(http, settings, session_factory):
                    return ImportResult(Outcome.UNCHANGED, None, "server reports the same file")
                source = fetch.download(
                    http,
                    settings.static_feed_url,
                    Path(workdir) / "feed.zip",
                    settings.static_max_download_bytes,
                )
            finally:
                if owns_client:
                    http.close()
            source_url = settings.static_feed_url

        with session_factory() as session:
            active = loader.get_active_version(session)
            if active is not None and active.sha256 == source.sha256 and not force:
                return ImportResult(Outcome.UNCHANGED, active.id, "identical content (sha256)")

        if not zipfile.is_zipfile(source.path):
            raise GtfsFormatError("downloaded file is not a zip archive")
        with zipfile.ZipFile(source.path) as zf:
            feed = parse_feed(zf)
        logger.info("parsed static feed: %s", feed.report())

        with session_factory.begin() as session:
            version = loader.load_version(session, feed, source, source_url, force=force)
            pruned = loader.prune_versions(session)
            version_id = version.id

        detail = (
            f"{len(feed.routes)} routes, {len(feed.stops)} stops, {len(feed.trips)} trips; "
            f"pruned versions {pruned}"
        )
        logger.info("activated static version %s: %s", version_id, detail)
        return ImportResult(Outcome.IMPORTED, version_id, detail)
