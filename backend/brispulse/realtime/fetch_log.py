"""Writes the collector's fetch records to the database."""

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from brispulse.models import FeedFetch
from brispulse.realtime.collector import FetchRecord


def make_fetch_recorder(session_factory: sessionmaker[Session]) -> Callable[[FetchRecord], None]:
    def record_fetch(record: FetchRecord) -> None:
        with session_factory.begin() as session:
            session.add(
                FeedFetch(
                    feed=record.feed.value,
                    fetched_at=record.fetched_at,
                    duration_ms=record.duration_ms,
                    outcome=record.outcome.value,
                    http_status=record.http_status,
                    body_bytes=record.body_bytes,
                    source_timestamp=record.source_timestamp,
                    entity_count=record.entity_count,
                    accepted_count=record.accepted_count,
                    rejected=dict(record.rejected) if record.rejected is not None else None,
                    anomaly=record.anomaly,
                    detail=record.detail,
                    static_version_id=record.static_version_id,
                )
            )

    return record_fetch
