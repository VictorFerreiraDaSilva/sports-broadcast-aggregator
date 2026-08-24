"""Processo principal do container: agenda as coletas de cada fonte registrada
e fica rodando.

O orquestrador não fixa horários — cada fonte declara sua própria cadência
(`games_schedule`, e `catalog_schedule` se ela sincronizar catálogo) e este
módulo só itera o registro (ADR 0001/0004). Adicionar uma fonte não muda
nada aqui.
"""

from __future__ import annotations

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import BRT, RUN_ON_STARTUP
from app.core.db import SessionLocal
from app.core.jobs import run_catalog_sync, run_games_scrape
from app.core.registry import SOURCES, seed_sources
from app.core.source import Source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def _run_games_job(source: Source) -> None:
    log.info("iniciando coleta de jogos: source=%s", source.code)
    result = run_games_scrape(source)
    log.info("coleta de jogos concluída: source=%s status=%s", source.code, result["status"])


def _run_catalog_job(source: Source) -> None:
    log.info("iniciando sincronização de catálogo: source=%s", source.code)
    result = run_catalog_sync(source)
    log.info("sincronização de catálogo concluída: source=%s status=%s", source.code, result["status"])


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=BRT)
    for source in SOURCES:
        for i, cron in enumerate(source.games_schedule):
            scheduler.add_job(
                _run_games_job,
                CronTrigger(hour=cron.hour, minute=cron.minute, timezone=BRT),
                args=[source],
                id=f"games_{source.code}_{i}",
            )

        sync_catalog = getattr(source, "sync_catalog", None)
        if sync_catalog is not None:
            for i, cron in enumerate(source.catalog_schedule):
                scheduler.add_job(
                    _run_catalog_job,
                    CronTrigger(hour=cron.hour, minute=cron.minute, timezone=BRT),
                    args=[source],
                    id=f"catalog_{source.code}_{i}",
                )
    return scheduler


def main() -> None:
    session = SessionLocal()
    seed_sources(session)
    session.close()

    scheduler = build_scheduler()

    if RUN_ON_STARTUP:
        log.info("RUN_ON_STARTUP=true: executando catálogos + jogos de todas as fontes imediatamente")
        for source in SOURCES:
            if getattr(source, "sync_catalog", None) is not None:
                _run_catalog_job(source)
            _run_games_job(source)

    log.info("scheduler iniciado — %d fonte(s) registrada(s): %s", len(SOURCES), [s.code for s in SOURCES])
    scheduler.start()


if __name__ == "__main__":
    main()
