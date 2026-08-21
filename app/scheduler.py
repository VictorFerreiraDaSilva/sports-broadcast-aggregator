"""Processo principal do container: agenda as coletas e fica rodando.

Horários dos jogos (pedido do projeto, horário de Brasília): 6:00, 12:00,
18:00 e 23:40. Catálogos (canais/competições) uma vez por dia, antes da
primeira coleta — eles mudam em escala de semanas
(docs/legal-e-etiqueta.md), então sincronizar 4x/dia seria desnecessário.
"""

from __future__ import annotations

import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import BRT, RUN_ON_STARTUP
from app.jobs import run_catalogs_sync, run_games_scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def _run_games_job() -> None:
    log.info("iniciando coleta de jogos")
    result = run_games_scrape()
    log.info("coleta de jogos concluída: status=%s", result["status"])


def _run_catalogs_job() -> None:
    log.info("iniciando sincronização de catálogos")
    result = run_catalogs_sync()
    log.info("sincronização de catálogos concluída: status=%s", result["status"])


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=BRT)
    scheduler.add_job(
        _run_games_job,
        CronTrigger(hour="6,12,18", minute="0", timezone=BRT),
        id="games_6_12_18",
    )
    scheduler.add_job(
        _run_games_job,
        CronTrigger(hour="23", minute="40", timezone=BRT),
        id="games_23_40",
    )
    scheduler.add_job(
        _run_catalogs_job,
        CronTrigger(hour="5", minute="55", timezone=BRT),
        id="catalogs_daily",
    )
    return scheduler


def main() -> None:
    scheduler = build_scheduler()

    if RUN_ON_STARTUP:
        log.info("RUN_ON_STARTUP=true: executando catálogos + jogos imediatamente")
        _run_catalogs_job()
        _run_games_job()

    log.info(
        "scheduler iniciado — próximas execuções às 6:00, 12:00, 18:00 e 23:40 (America/Sao_Paulo)"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
