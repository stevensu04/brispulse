"""How fresh is a feed? (architecture §7)

Freshness is judged at the moment of asking, from the feed's own timestamp. A feed
that stops updating degrades through the states by itself; nothing has to notice the
failure and flip a flag.
"""

import enum

from brispulse.realtime.model import FeedName
from brispulse.realtime.thresholds import FRESHNESS_LIMITS


class Freshness(enum.StrEnum):
    LIVE = "live"
    DELAYED = "delayed"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


def feed_freshness(feed: FeedName, source_timestamp: int | None, now: float) -> Freshness:
    """Classify a feed by the age of its data.

    ``source_timestamp`` is None when the feed has never been fetched successfully.
    """
    if source_timestamp is None:
        return Freshness.UNAVAILABLE
    limits = FRESHNESS_LIMITS[feed]
    age = now - source_timestamp
    if age <= limits.live_s:
        return Freshness.LIVE
    if age <= limits.delayed_s:
        return Freshness.DELAYED
    if age <= limits.stale_s:
        return Freshness.STALE
    return Freshness.UNAVAILABLE


def data_is_usable(freshness: Freshness) -> bool:
    """Whether live values may be shown at all. Unavailable data is withheld, not zeroed."""
    return freshness is not Freshness.UNAVAILABLE
