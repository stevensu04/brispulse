import datetime as dt
import hashlib
from pathlib import Path

import httpx2
import pytest

from brispulse.gtfs_static import fetch

URL = "https://translink.test/GTFS/SEQ_GTFS.zip"
HEADERS = {"ETag": '"0xABC"', "Last-Modified": "Fri, 13 Nov 2026 19:45:24 GMT"}


def client_returning(handler: httpx2.MockTransport) -> httpx2.Client:
    return httpx2.Client(transport=handler)


def test_head_reads_version_markers() -> None:
    client = client_returning(
        httpx2.MockTransport(lambda request: httpx2.Response(200, headers=HEADERS))
    )

    info = fetch.head(client, URL)

    assert info.etag == '"0xABC"'
    assert info.last_modified == dt.datetime(2026, 11, 13, 19, 45, 24, tzinfo=dt.UTC)


def test_head_tolerates_missing_or_malformed_markers() -> None:
    client = client_returning(
        httpx2.MockTransport(
            lambda request: httpx2.Response(200, headers={"Last-Modified": "soon"})
        )
    )

    assert fetch.head(client, URL) == fetch.RemoteInfo(etag=None, last_modified=None)


def test_head_failure_is_a_fetch_error() -> None:
    client = client_returning(httpx2.MockTransport(lambda request: httpx2.Response(503)))

    with pytest.raises(fetch.FetchError, match="HTTP 503"):
        fetch.head(client, URL)


def test_network_failure_is_a_fetch_error() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectTimeout("timed out")

    with pytest.raises(fetch.FetchError, match="timed out"):
        fetch.head(client_returning(httpx2.MockTransport(refuse)), URL)


def test_download_writes_file_and_hashes_it(tmp_path: Path) -> None:
    body = b"zip-bytes" * 1000
    client = client_returning(
        httpx2.MockTransport(lambda request: httpx2.Response(200, content=body, headers=HEADERS))
    )

    result = fetch.download(client, URL, tmp_path / "feed.zip", max_bytes=1_000_000)

    assert result.path.read_bytes() == body
    assert result.sha256 == hashlib.sha256(body).hexdigest()
    assert result.size_bytes == len(body)
    assert result.remote.etag == '"0xABC"'


def test_download_sends_the_configured_user_agent(tmp_path: Path) -> None:
    seen: list[str] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["user-agent"])
        return httpx2.Response(200, content=b"x")

    client = httpx2.Client(
        transport=httpx2.MockTransport(record), headers={"User-Agent": "BrisPulse/test"}
    )
    fetch.download(client, URL, tmp_path / "feed.zip", max_bytes=10)

    assert seen == ["BrisPulse/test"]


def test_download_rejects_an_oversized_body(tmp_path: Path) -> None:
    client = client_returning(
        httpx2.MockTransport(lambda request: httpx2.Response(200, content=b"x" * 2048))
    )

    with pytest.raises(fetch.FetchError, match="exceeds"):
        fetch.download(client, URL, tmp_path / "feed.zip", max_bytes=1024)


def test_download_rejects_an_empty_body(tmp_path: Path) -> None:
    client = client_returning(
        httpx2.MockTransport(lambda request: httpx2.Response(200, content=b""))
    )

    with pytest.raises(fetch.FetchError, match="empty"):
        fetch.download(client, URL, tmp_path / "feed.zip", max_bytes=1024)


def test_download_rejects_an_error_status(tmp_path: Path) -> None:
    client = client_returning(httpx2.MockTransport(lambda request: httpx2.Response(404)))

    with pytest.raises(fetch.FetchError, match="HTTP 404"):
        fetch.download(client, URL, tmp_path / "feed.zip", max_bytes=1024)


def test_describe_local_file_hashes_without_remote_markers(tmp_path: Path) -> None:
    path = tmp_path / "feed.zip"
    path.write_bytes(b"local")

    result = fetch.describe_local_file(path)

    assert result.sha256 == hashlib.sha256(b"local").hexdigest()
    assert result.size_bytes == 5
    assert result.remote == fetch.RemoteInfo(etag=None, last_modified=None)
