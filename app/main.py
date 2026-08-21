"""CLI para rodar um job manualmente, fora do agendamento — útil para testar.

    python -m app.main scrape      # coleta jogos (hoje + 3 dias, 5 esportes)
    python -m app.main catalogs    # sincroniza canais.json + competicoes-futebol.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.jobs import run_catalogs_sync, run_games_scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("job", choices=["scrape", "catalogs"])
    args = ap.parse_args()

    result = run_games_scrape() if args.job == "scrape" else run_catalogs_sync()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
