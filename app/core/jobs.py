"""Wrappers genéricos que abrem sessão, chamam uma fonte e gravam o resultado
em `scrape_run` — usados pelo scheduler e pelo CLI manual (app/main.py).

Erros por data/requisição dentro de `fetch_games` são responsabilidade da
própria fonte (logar e pular) — o que chega até aqui é só o total de jogos
coletados na execução. Uma falha que a fonte não conseguiu engolir (erro de
rede fatal, exceção de programação, ...) propaga e marca o run como "error".
"""

from __future__ import annotations

import datetime as dt
import logging

from app.core.db import SessionLocal
from app.core.ingest import target_dates, upsert_games
from app.core.models import ScrapeRun
from app.core.source import Source

log = logging.getLogger(__name__)


def _run(job_type: str, source: Source, fn) -> dict:
    started_at = dt.datetime.now(dt.timezone.utc)
    session = SessionLocal()
    status = "success"
    details: dict = {}
    error_message = None
    try:
        details = fn(session)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - precisa registrar qualquer falha
        session.rollback()
        status = "error"
        error_message = str(exc)
        log.exception("job %s (source=%s) falhou", job_type, source.code)
    finally:
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
        session.close()

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
        raise TypeError(f"fonte {source.code!r} não implementa sync_catalog (ADR 0004)")
    return _run("catalog", source, lambda session: sync_catalog(session))
