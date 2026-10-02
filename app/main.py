"""CLI to run a job by hand, outside the schedule — handy for testing.

    python -m app.main games                  # collect games from every source
    python -m app.main games --source futnatv # from one source only
    python -m app.main catalog                # sync the catalog of every source that has one
    python -m app.main catalog --source futnatv
    python -m app.main reclassify             # re-apply app/core/classification.py to stored games
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.core.db import SessionLocal
from app.core.ingest import reclassify_games
from app.core.jobs import run_catalog_sync, run_games_scrape
from app.core.registry import SOURCES, get_source, seed_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("job", choices=["games", "catalog", "reclassify"])
    ap.add_argument("--source", help="source code (default: every registered one)")
    args = ap.parse_args()

    # Reclassification reads no source: it re-applies the curated lists and the
    # name patterns to games already stored (see app/core/ingest.py).
    if args.job == "reclassify":
        session = SessionLocal()
        result = reclassify_games(session)
        session.commit()
        session.close()
        print(json.dumps(result, indent=2))
        return

    sources = [get_source(args.source)] if args.source else SOURCES

    session = SessionLocal()
    seed_sources(session)
    session.close()

    results = {}
    for source in sources:
        if args.job == "catalog":
            if getattr(source, "sync_catalog", None) is None:
                continue
            results[source.code] = run_catalog_sync(source)
        else:
            results[source.code] = run_games_scrape(source)

    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
