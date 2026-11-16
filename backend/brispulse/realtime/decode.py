"""Decode a GTFS-Realtime response and judge it as a whole.

Record-level validation lives in ``normalise``. This module answers a prior question:
is this response a usable, newer copy of the feed at all?
"""

import enum
from dataclasses import dataclass

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from brispulse.realtime.thresholds import Thresholds


class FeedDecodeError(Exception):
    """The response body is not a GTFS-Realtime message."""


class HeaderVerdict(enum.StrEnum):
    OK = "ok"
    # Same timestamp as the data already held: nothing new to process.
    UNCHANGED = "unchanged"
    # Older than the data already held (a cache can serve an earlier copy).
    STALE_RESPONSE = "stale_response"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class HeaderCheck:
    verdict: HeaderVerdict
    reason: str | None = None


def decode_feed(body: bytes) -> gtfs_realtime_pb2.FeedMessage:
    """Parse ``body`` as a ``FeedMessage``."""
    message = gtfs_realtime_pb2.FeedMessage()
    try:
        message.ParseFromString(body)
    except DecodeError as exc:
        raise FeedDecodeError(str(exc)) from exc
    # An empty or truncated body can parse "successfully" into a message without the
    # required header, so the header is checked explicitly.
    if not message.HasField("header") or not message.header.gtfs_realtime_version:
        raise FeedDecodeError("message has no GTFS-Realtime header")
    return message


def check_header(
    message: gtfs_realtime_pb2.FeedMessage,
    *,
    now: float,
    previous_timestamp: int | None,
    thresholds: Thresholds,
) -> HeaderCheck:
    header = message.header
    # Accept 2.x: a minor revision only adds optional fields. Anything else is unknown.
    if header.gtfs_realtime_version.split(".")[0] != "2":
        return HeaderCheck(
            HeaderVerdict.REJECTED, f"unsupported_version_{header.gtfs_realtime_version}"
        )
    if not header.timestamp:
        return HeaderCheck(HeaderVerdict.REJECTED, "missing_timestamp")
    if header.timestamp > now + thresholds.future_tolerance_s:
        return HeaderCheck(HeaderVerdict.REJECTED, "future_timestamp")
    if previous_timestamp is not None:
        if header.timestamp == previous_timestamp:
            return HeaderCheck(HeaderVerdict.UNCHANGED)
        if header.timestamp < previous_timestamp:
            return HeaderCheck(HeaderVerdict.STALE_RESPONSE)
    return HeaderCheck(HeaderVerdict.OK)
