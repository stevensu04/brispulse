"""Logging configuration shared by the service and its command-line tools."""

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx2 logs every request at INFO, which would drown the collector's own records.
    logging.getLogger("httpx2").setLevel(logging.WARNING)
