"""CLI para rodar um job manualmente, fora do agendamento — útil para testar.

    python -m app.main games                 # coleta jogos de todas as fontes
    python -m app.main games --source futnatv # só de uma fonte
    python -m app.main catalog                # sincroniza o catálogo de toda fonte que tiver um
    python -m app.main catalog --source futnatv
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.core.db import SessionLocal
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
    ap.add_argument("job", choices=["games", "catalog"])
    ap.add_argument("--source", help="código da fonte (default: todas as registradas)")
    args = ap.parse_args()

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
