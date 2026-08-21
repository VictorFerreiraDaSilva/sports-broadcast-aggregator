"""Wrappers de app/ingest.py e app/catalogs.py que abrem sessão, chamam a API
e gravam o resultado em `scrape_run` — usados pelo scheduler e pelo CLI manual.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.catalogs import sync_all_catalogs
from app.client import Futnatv
from app.db import SessionLocal
from app.ingest import scrape_games
from app.models import ScrapeRun

log = logging.getLogger(__name__)


def _run(job_type: str, fn) -> dict:
    started_at = dt.datetime.now(dt.timezone.utc)
    session = SessionLocal()
    client = Futnatv()
    status = "success"
    details: dict = {}
    error_message = None
    try:
        details = fn(session, client)
        if details.get("errors"):
            status = "partial"
    except Exception as exc:  # noqa: BLE001 - precisa registrar qualquer falha
        session.rollback()
        status = "error"
        error_message = str(exc)
        log.exception("job %s falhou", job_type)
    finally:
        run = ScrapeRun(
            job_type=job_type,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            status=status,
            details=details,
            error_message=error_message,
        )
        session.add(run)
        session.commit()
        session.close()

    return {"status": status, "details": details, "error_message": error_message}


def run_games_scrape() -> dict:
    return _run("games", scrape_games)


def run_catalogs_sync() -> dict:
    return _run("catalogs", sync_all_catalogs)
