"""Download the static GTFS zip from TransLink."""

import datetime as dt
import hashlib
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx2

from brispulse.config import Settings


class FetchError(Exception):
    """The file could not be retrieved, or is not what was expected."""


@dataclass(frozen=True, slots=True)
class RemoteInfo:
    """Version markers the server reports for the file."""

    etag: str | None
    last_modified: dt.datetime | None


@dataclass(frozen=True, slots=True)
class Download:
    path: Path
    sha256: str
    size_bytes: int
    remote: RemoteInfo


def make_client(settings: Settings) -> httpx2.Client:
    return httpx2.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=httpx2.Timeout(settings.static_download_timeout_seconds, connect=10.0),
        follow_redirects=True,
    )


def _remote_info(response: httpx2.Response) -> RemoteInfo:
    last_modified: dt.datetime | None = None
    header = response.headers.get("last-modified")
    if header:
        try:
            last_modified = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            last_modified = None
    return RemoteInfo(etag=response.headers.get("etag"), last_modified=last_modified)


def head(client: httpx2.Client, url: str) -> RemoteInfo:
    """Ask the server for the file's version markers without downloading it."""
    try:
        response = client.head(url)
    except httpx2.HTTPError as exc:
        raise FetchError(f"HEAD {url} failed: {exc}") from exc
    if response.status_code != 200:
        raise FetchError(f"HEAD {url} returned HTTP {response.status_code}")
    return _remote_info(response)


def download(client: httpx2.Client, url: str, dest: Path, max_bytes: int) -> Download:
    """Stream the file to ``dest``, hashing it on the way."""
    digest = hashlib.sha256()
    size = 0
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise FetchError(f"GET {url} returned HTTP {response.status_code}")
            remote = _remote_info(response)
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError(f"{url} exceeds the {max_bytes}-byte limit")
                    digest.update(chunk)
                    handle.write(chunk)
    except httpx2.HTTPError as exc:
        raise FetchError(f"GET {url} failed: {exc}") from exc
    if size == 0:
        raise FetchError(f"{url} returned an empty body")
    return Download(path=dest, sha256=digest.hexdigest(), size_bytes=size, remote=remote)


def describe_local_file(path: Path) -> Download:
    """Treat a zip already on disk as a download (used for manual imports and tests)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return Download(
        path=path,
        sha256=digest.hexdigest(),
        size_bytes=path.stat().st_size,
        remote=RemoteInfo(etag=None, last_modified=None),
    )
