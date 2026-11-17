from typing import Any

import pytest

from brispulse.realtime.decode import (
    FeedDecodeError,
    HeaderVerdict,
    check_header,
    decode_feed,
)
from brispulse.realtime.thresholds import DEFAULT_THRESHOLDS
from tests.rt_fixture import NOW, feed, feed_bytes, vehicle


def test_decodes_a_feed() -> None:
    message = decode_feed(feed_bytes(vehicle("V1"), vehicle("V2")))

    assert message.header.timestamp == NOW
    assert len(message.entity) == 2


@pytest.mark.parametrize(
    "body",
    [b"", b"<html>Service unavailable</html>", b"\x00\x01\x02garbage", feed_bytes()[:3]],
    ids=["empty", "html", "garbage", "truncated"],
)
def test_bodies_that_are_not_a_feed_are_decode_errors(body: bytes) -> None:
    with pytest.raises(FeedDecodeError):
        decode_feed(body)


def verdict(message: Any, previous: int | None = None, now: float = NOW + 30) -> HeaderVerdict:
    return check_header(
        message, now=now, previous_timestamp=previous, thresholds=DEFAULT_THRESHOLDS
    ).verdict


def test_a_first_feed_is_accepted() -> None:
    assert verdict(feed()) is HeaderVerdict.OK


def test_a_newer_feed_is_accepted() -> None:
    assert verdict(feed(timestamp=NOW), previous=NOW - 20) is HeaderVerdict.OK


def test_the_same_timestamp_means_nothing_new() -> None:
    assert verdict(feed(timestamp=NOW), previous=NOW) is HeaderVerdict.UNCHANGED


def test_an_older_timestamp_is_a_stale_response() -> None:
    assert verdict(feed(timestamp=NOW - 40), previous=NOW) is HeaderVerdict.STALE_RESPONSE


@pytest.mark.parametrize(
    ("version", "expected"),
    [("2.0", "ok"), ("2.1", "ok"), ("1.0", "rejected"), ("3.0", "rejected")],
)
def test_only_version_2_is_supported(version: str, expected: str) -> None:
    assert verdict(feed(version=version)).value == expected


def test_a_feed_without_a_timestamp_is_rejected() -> None:
    check = check_header(
        feed(timestamp=None), now=NOW, previous_timestamp=None, thresholds=DEFAULT_THRESHOLDS
    )

    assert (check.verdict, check.reason) == (HeaderVerdict.REJECTED, "missing_timestamp")


def test_a_feed_from_the_future_is_rejected_beyond_the_tolerance() -> None:
    tolerance = DEFAULT_THRESHOLDS.future_tolerance_s

    assert verdict(feed(timestamp=NOW + tolerance), now=NOW) is HeaderVerdict.OK
    assert verdict(feed(timestamp=NOW + tolerance + 1), now=NOW) is HeaderVerdict.REJECTED
