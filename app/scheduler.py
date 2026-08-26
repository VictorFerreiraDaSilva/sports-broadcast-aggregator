"""Processo principal do container: agenda as coletas de cada fonte registrada
e fica rodando.

O orquestrador não fixa horários — cada fonte declara sua própria cadência
(`games_schedule`, e `catalog_schedule` se ela sincronizar catálogo) e este
módulo só itera o registro (ADR 0001/0004). Adicionar uma fonte não muda
nada aqui.

Notificação (ADR 0007): o resultado de cada coleta é notificado por
`app/core/jobs.py`, não aqui. Este módulo cobre só o que acontece *fora* de uma
coleta — o boot e os eventos do próprio APScheduler (job que estourou por um
caminho que `jobs._run` não pegou, ou execução perdida).
"""

from __future__ import annotations

import logging
import os
import sys

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import BRT, RUN_ON_STARTUP
from app.core.db import SessionLocal
from app.core.jobs import run_catalog_sync, run_games_scrape
from app.core.notify import PRIORITY_CRITICAL, PRIORITY_WARNING, notify
from app.core.registry import SOURCES, seed_sources
from app.core.source import Source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# Tolerância para um job que não pôde disparar na hora exata (container ocupado,
# máquina suspensa). O default do APScheduler é 1 segundo, o que faria qualquer
# atraso trivial contar como execução perdida e virar notificação. 5 minutos
# separa "atrasou" de "perdeu mesmo".
MISFIRE_GRACE_SECONDS = int(os.environ.get("MISFIRE_GRACE_SECONDS", "300"))

# Marcador para não repetir a notificação de falha de boot a cada reinício.
# Uma falha de boot é determinística: sem isso, `restart: unless-stopped`
# transformaria um erro em push a cada poucos segundos, indefinidamente. O
# arquivo sobrevive a `docker compose restart` e some quando o container é
# recriado (`up --build`), que é exatamente o momento em que faz sentido
# notificar de novo.
BOOT_ALERT_MARKER = os.environ.get("BOOT_ALERT_MARKER", "/tmp/fut-boot-alert")


def _run_games_job(source: Source) -> None:
    log.info("iniciando coleta de jogos: source=%s", source.code)
    result = run_games_scrape(source)
    log.info("coleta de jogos concluída: source=%s status=%s", source.code, result["status"])


def _run_catalog_job(source: Source) -> None:
    log.info("iniciando sincronização de catálogo: source=%s", source.code)
    result = run_catalog_sync(source)
    log.info("sincronização de catálogo concluída: source=%s status=%s", source.code, result["status"])


def _on_scheduler_event(event) -> None:
    """Rede de segurança do APScheduler (ADR 0007).

    `jobs._run` já captura e notifica qualquer falha *dentro* de uma coleta, de
    modo que `EVENT_JOB_ERROR` aqui significa algo que escapou dele — falha ao
    gravar o próprio `scrape_run`, por exemplo. `EVENT_JOB_MISSED` é o outro
    buraco: nenhuma exceção acontece, o job simplesmente não rodou.
    """
    if event.code == EVENT_JOB_ERROR:
        log.exception(
            "job %s do scheduler estourou fora de jobs._run", event.job_id, exc_info=event.exception
        )
        notify(
            "job do scheduler estourou",
            f"O job {event.job_id} levantou uma exceção que jobs._run não capturou "
            "— provável falha ao gravar scrape_run.\n\n"
            f"{type(event.exception).__name__}: {event.exception}",
            priority=PRIORITY_WARNING,
        )
    elif event.code == EVENT_JOB_MISSED:
        log.error("execução perdida: job=%s horário=%s", event.job_id, event.scheduled_run_time)
        notify(
            "execução perdida",
            f"O job {event.job_id} deveria ter rodado às {event.scheduled_run_time} "
            f"e não rodou (atraso acima de {MISFIRE_GRACE_SECONDS}s).\n"
            "Container ocupado, suspenso ou reiniciando na hora agendada.",
            priority=PRIORITY_WARNING,
        )


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=BRT)
    scheduler.add_listener(_on_scheduler_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    for source in SOURCES:
        for i, cron in enumerate(source.games_schedule):
            scheduler.add_job(
                _run_games_job,
                CronTrigger(hour=cron.hour, minute=cron.minute, timezone=BRT),
                args=[source],
                id=f"games_{source.code}_{i}",
                misfire_grace_time=MISFIRE_GRACE_SECONDS,
            )

        sync_catalog = getattr(source, "sync_catalog", None)
        if sync_catalog is not None:
            for i, cron in enumerate(source.catalog_schedule):
                scheduler.add_job(
                    _run_catalog_job,
                    CronTrigger(hour=cron.hour, minute=cron.minute, timezone=BRT),
                    args=[source],
                    id=f"catalog_{source.code}_{i}",
                    misfire_grace_time=MISFIRE_GRACE_SECONDS,
                )
    return scheduler


def _notify_boot_failure(exc: Exception) -> None:
    """Notifica falha de inicialização, no máximo uma vez por container."""
    try:
        already_alerted = os.path.exists(BOOT_ALERT_MARKER)
    except OSError:
        already_alerted = False

    if already_alerted:
        log.error("falha de boot repetida — notificação já enviada neste container")
        return

    notify(
        "falha na inicialização",
        "O scheduler não conseguiu subir. Nenhuma coleta vai rodar até isso ser "
        "resolvido.\n\n"
        f"{type(exc).__name__}: {exc}",
        priority=PRIORITY_CRITICAL,
    )
    try:
        with open(BOOT_ALERT_MARKER, "w") as fh:
            fh.write(f"{type(exc).__name__}: {exc}\n")
    except OSError as write_exc:
        log.warning("não foi possível gravar o marcador de boot: %s", write_exc)


def main() -> None:
    # `wait_for_db` (docker/entrypoint.sh) já garantiu que o banco responde, e o
    # alembic já rodou — uma falha aqui é bug de verdade, não indisponibilidade.
    try:
        session = SessionLocal()
        seed_sources(session)
        session.close()
        scheduler = build_scheduler()
    except Exception as exc:  # noqa: BLE001 - boot mudo é o pior modo de falha
        log.exception("falha ao inicializar o scheduler")
        _notify_boot_failure(exc)
        raise

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
