import pytest

from brispulse.realtime.freshness import Freshness, data_is_usable, feed_freshness
from brispulse.realtime.model import FeedName

T0 = 1_800_000_000


@pytest.mark.parametrize("feed", [FeedName.VEHICLE_POSITIONS, FeedName.TRIP_UPDATES])
@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, Freshness.LIVE),
        (90, Freshness.LIVE),
        (91, Freshness.DELAYED),
        (300, Freshness.DELAYED),
        (301, Freshness.STALE),
        (900, Freshness.STALE),
        (901, Freshness.UNAVAILABLE),
        (86_400, Freshness.UNAVAILABLE),
    ],
)
def test_vehicle_and_trip_feeds_degrade_with_age(
    feed: FeedName, age: int, expected: Freshness
) -> None:
    assert feed_freshness(feed, T0, T0 + age) is expected


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (600, Freshness.LIVE),
        (601, Freshness.DELAYED),
        (1800, Freshness.DELAYED),
        (1801, Freshness.STALE),
        (7200, Freshness.STALE),
        (7201, Freshness.UNAVAILABLE),
    ],
)
def test_alerts_are_allowed_to_be_older(age: int, expected: Freshness) -> None:
    assert feed_freshness(FeedName.ALERTS, T0, T0 + age) is expected


@pytest.mark.parametrize("feed", list(FeedName))
def test_a_feed_never_fetched_is_unavailable(feed: FeedName) -> None:
    assert feed_freshness(feed, None, T0) is Freshness.UNAVAILABLE


def test_a_clock_slightly_behind_the_feed_still_reads_as_live() -> None:
    assert feed_freshness(FeedName.VEHICLE_POSITIONS, T0, T0 - 5) is Freshness.LIVE


def test_only_unavailable_data_is_withheld() -> None:
    assert [data_is_usable(state) for state in Freshness] == [True, True, True, False]
