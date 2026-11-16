"""Command line: ``python -m brispulse.gtfs_static {check,import}``."""

import argparse
import logging
import sys
from pathlib import Path

from brispulse.config import get_settings
from brispulse.db import make_engine, make_session_factory
from brispulse.gtfs_static import fetch, loader, service
from brispulse.gtfs_static.parse import GtfsFormatError
from brispulse.logging_setup import configure_logging

logger = logging.getLogger("brispulse.gtfs_static")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m brispulse.gtfs_static")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="report whether TransLink has published a new file")
    importer = commands.add_parser("import", help="download and load the static feed")
    importer.add_argument("--file", type=Path, help="import this zip instead of downloading")
    importer.add_argument(
        "--force",
        action="store_true",
        help="re-import an unchanged file and skip the shrink guard",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.require_database_url())
    session_factory = make_session_factory(engine)

    try:
        if args.command == "check":
            with fetch.make_client(settings) as client:
                changed = service.remote_has_changed(client, settings, session_factory)
            print("changed" if changed else "unchanged")
            return 0

        result = service.run_import(
            settings, session_factory, local_file=args.file, force=args.force
        )
        print(f"{result.outcome}: {result.detail}")
        return 0
    except (
        fetch.FetchError,
        GtfsFormatError,
        loader.EmptyFeedError,
        loader.SuspiciousFeedError,
    ) as exc:
        # Expected failure modes: report them plainly. The active version is untouched.
        logger.error("static import failed: %s", exc)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
