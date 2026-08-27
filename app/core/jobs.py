"""Generic wrappers that open a session, call a source, write the result to
`scrape_run` and notify if something went wrong — used by the scheduler and by
the manual CLI (app/main.py).

Per-date/per-request errors inside `fetch_games` remain the source's own
responsibility (log and skip). What changed (ADR 0007) is that this `log.error`
is no longer invisible: `collect_errors()` captures it, and a run that
"succeeded" but swallowed failures leaves here as *degraded* —
`scrape_run.status="degraded"`, with the errors aggregated into
`scrape_run.details`, plus a warning push. A failure the source could not
swallow (fatal network error, programming exception, ...) propagates, marks the
run as "error" and notifies.

`status` therefore has three values: `success` (clean), `degraded` (wrote what
it could, swallowed errors) and `error` (lost the entire run). An `error` run
that also swallowed partial errors stays `error` — the fatal failure is the
more severe one — but carries the partials in `details` all the same, where
they used to be lost.

At most one notification per run — see `_notify_result`. Without that, the
source's API being down would generate a dozen pushes per run, on precisely the
day reading the phone matters.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.core.db import SessionLocal
from app.core.errors import CollectedErrors, collect_errors
from app.core.ingest import target_dates, upsert_games
from app.core.models import ScrapeRun
from app.core.notify import PRIORITY_ERROR, PRIORITY_WARNING, notify
from app.core.source import Source

log = logging.getLogger(__name__)


def _notify_result(
    job_type: str,
    source: Source,
    status: str,
    details: dict,
    error_message: str | None,
    collected: CollectedErrors,
    run_id: int | None,
) -> None:
    """Decide whether this run deserves a push, and at which severity (ADR 0007).

    Three situations notify, in order of severity:

    - **failed**: the entire run was lost. Normal priority — the next scheduled
      run may well fix it on its own.
    - **degraded**: wrote something, but swallowed errors along the way.
    - **no games**: not a single error, and still no game came through. It is
      the quietest failure mode here (the source answers 200 and the parser
      accepts it, but finds nothing) and the only one no exception reveals.

    A clean run does not notify — one push per successful collection, 4x a day
    per source, would train anyone to ignore the pushes.
    """
    job_label = f"{source.code}/{job_type}"
    run_label = f"run #{run_id}" if run_id is not None else "run not recorded"

    if status == "error":
        parts = [error_message or "error with no message"]
        if collected:
            parts.append(f"\nBefore failing:\n{collected.summary()}")
        parts.append(f"\n{run_label}")
        notify(f"{job_label} failed", "\n".join(parts), priority=PRIORITY_ERROR)
        return

    if collected:
        plural = "errors" if collected.total > 1 else "error"
        parts = [
            f"{collected.total} {plural} swallowed during the run.",
            "",
            collected.summary(),
            "",
            f"{_details_label(job_type, details)} · {run_label}",
        ]
        notify(f"{job_label} degraded", "\n".join(parts), priority=PRIORITY_WARNING)
        return

    if job_type == "games" and details.get("games_count") == 0:
        notify(
            f"{job_label} no games",
            "The run finished without a single error and wrote no games.\n"
            "Likely a contract change at the source: it answered, the parser "
            "accepted it, and nothing was left.\n\n"
            f"{run_label}",
            priority=PRIORITY_WARNING,
        )


def _details_label(job_type: str, details: dict) -> str:
    if job_type == "games":
        return f"{details.get('games_count', 0)} game(s) written"
    return "catalog synced"


def _run(job_type: str, source: Source, fn) -> dict:
    started_at = dt.datetime.now(dt.timezone.utc)
    session = SessionLocal()
    status = "success"
    details: dict = {}
    error_message = None
    run_id = None
    collected = CollectedErrors()

    try:
        # Only `fn` sits under the collector: the `log.exception` below is the
        # total failure, already reported through `error_message`, and must not
        # enter the aggregation of partial errors.
        with collect_errors() as collected:
            details = fn(session)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - must record any failure whatsoever
        session.rollback()
        status = "error"
        error_message = f"{type(exc).__name__}: {exc}"
        log.exception("job %s (source=%s) failed", job_type, source.code)
    finally:
        # The "degraded" state (wrote, but swallowed errors) has to exist in
        # the database, not only in the push: a run that merely notified must
        # not be counted as a clean success by whoever queries `scrape_run`
        # later. `error_message` stays reserved for the fatal failure — the
        # swallowed errors go into `details`, structured.
        if collected:
            details = {
                **details,
                "errors_collected": collected.total,
                "error_groups": collected.as_records(),
            }
            if status != "error":
                status = "degraded"

        run = ScrapeRun(
            source_code=source.code,
            job_type=job_type,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            status=status,
            details=details,
            error_message=error_message,
        )
        session.add(run)
        session.commit()
        run_id = run.id
        session.close()

    # Outside the finally and after the commit: the notification must never
    # keep `scrape_run` from being written, and it cites the run id for whoever
    # investigates.
    _notify_result(job_type, source, status, details, error_message, collected, run_id)

    return {"status": status, "details": details, "error_message": error_message}


def run_games_scrape(source: Source, dates: list[dt.date] | None = None) -> dict:
    def fn(session):
        games = source.fetch_games(session, dates or target_dates())
        count = upsert_games(session, source.code, games)
        return {"games_count": count}

    return _run("games", source, fn)


def run_catalog_sync(source: Source) -> dict:
    sync_catalog = getattr(source, "sync_catalog", None)
    if sync_catalog is None:
        raise TypeError(f"source {source.code!r} does not implement sync_catalog (ADR 0004)")
    return _run("catalog", source, lambda session: sync_catalog(session))
