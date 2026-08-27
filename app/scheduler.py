"""The container's main process: schedules each registered source's collections
and stays running.

The orchestrator fixes no times — each source declares its own cadence
(`games_schedule`, and `catalog_schedule` if it syncs a catalog) and this module
only iterates the registry (ADR 0001/0004). Adding a source changes nothing
here.

Notification (ADR 0007): the result of each collection is notified by
`app/core/jobs.py`, not here. This module covers only what happens *outside* a
collection — the boot and APScheduler's own events (a job that blew up through
a path `jobs._run` did not catch, or a missed run).
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

# Grace for a job that could not fire at the exact time (busy container,
# suspended machine). APScheduler's default is 1 second, which would make any
# trivial delay count as a missed run and become a notification. 5 minutes
# separates "ran late" from "actually missed".
MISFIRE_GRACE_SECONDS = int(os.environ.get("MISFIRE_GRACE_SECONDS", "300"))

# Marker to avoid repeating the boot-failure notification on every restart.
# A boot failure is deterministic: without this, `restart: unless-stopped` would
# turn one error into a push every few seconds, indefinitely. The file survives
# `docker compose restart` and disappears when the container is recreated
# (`up --build`), which is exactly when notifying again makes sense.
BOOT_ALERT_MARKER = os.environ.get("BOOT_ALERT_MARKER", "/tmp/fut-boot-alert")


def _run_games_job(source: Source) -> None:
    log.info("starting games collection: source=%s", source.code)
    result = run_games_scrape(source)
    log.info("games collection finished: source=%s status=%s", source.code, result["status"])


def _run_catalog_job(source: Source) -> None:
    log.info("starting catalog sync: source=%s", source.code)
    result = run_catalog_sync(source)
    log.info("catalog sync finished: source=%s status=%s", source.code, result["status"])


def _on_scheduler_event(event) -> None:
    """APScheduler safety net (ADR 0007).

    `jobs._run` already catches and notifies any failure *inside* a collection,
    so an `EVENT_JOB_ERROR` here means something escaped it — a failure writing
    `scrape_run` itself, for instance. `EVENT_JOB_MISSED` is the other hole: no
    exception happens, the job simply did not run.
    """
    if event.code == EVENT_JOB_ERROR:
        log.exception(
            "scheduler job %s blew up outside jobs._run", event.job_id, exc_info=event.exception
        )
        notify(
            "scheduler job blew up",
            f"Job {event.job_id} raised an exception jobs._run did not catch "
            "— likely a failure writing scrape_run.\n\n"
            f"{type(event.exception).__name__}: {event.exception}",
            priority=PRIORITY_WARNING,
        )
    elif event.code == EVENT_JOB_MISSED:
        log.error("missed run: job=%s time=%s", event.job_id, event.scheduled_run_time)
        notify(
            "missed run",
            f"Job {event.job_id} should have run at {event.scheduled_run_time} "
            f"and did not (delay above {MISFIRE_GRACE_SECONDS}s).\n"
            "Container busy, suspended or restarting at the scheduled time.",
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
    """Notify a startup failure, at most once per container."""
    try:
        already_alerted = os.path.exists(BOOT_ALERT_MARKER)
    except OSError:
        already_alerted = False

    if already_alerted:
        log.error("repeated boot failure — notification already sent in this container")
        return

    notify(
        "startup failure",
        "The scheduler could not come up. No collection will run until this is "
        "resolved.\n\n"
        f"{type(exc).__name__}: {exc}",
        priority=PRIORITY_CRITICAL,
    )
    try:
        with open(BOOT_ALERT_MARKER, "w") as fh:
            fh.write(f"{type(exc).__name__}: {exc}\n")
    except OSError as write_exc:
        log.warning("could not write the boot marker: %s", write_exc)


def main() -> None:
    # `wait_for_db` (docker/entrypoint.sh) has already ensured the database
    # answers, and alembic has already run — a failure here is a real bug, not
    # unavailability.
    try:
        session = SessionLocal()
        seed_sources(session)
        session.close()
        scheduler = build_scheduler()
    except Exception as exc:  # noqa: BLE001 - a mute boot is the worst failure mode
        log.exception("failed to initialize the scheduler")
        _notify_boot_failure(exc)
        raise

    if RUN_ON_STARTUP:
        log.info("RUN_ON_STARTUP=true: running catalogs + games for every source immediately")
        for source in SOURCES:
            if getattr(source, "sync_catalog", None) is not None:
                _run_catalog_job(source)
            _run_games_job(source)

    log.info("scheduler started — %d registered source(s): %s", len(SOURCES), [s.code for s in SOURCES])
    scheduler.start()


if __name__ == "__main__":
    main()
