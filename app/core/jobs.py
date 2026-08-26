"""Wrappers genéricos que abrem sessão, chamam uma fonte, gravam o resultado
em `scrape_run` e notificam se algo deu errado — usados pelo scheduler e pelo
CLI manual (app/main.py).

Erros por data/requisição dentro de `fetch_games` continuam sendo
responsabilidade da própria fonte (logar e pular). O que mudou (ADR 0007) é que
esse `log.error` deixou de ser invisível: `collect_errors()` o captura, e uma
execução que "deu certo" mas engoliu falhas sai daqui como *degradada* —
`scrape_run.status="degraded"`, com os erros agregados em
`scrape_run.details`, e push de aviso. Uma falha que a fonte não conseguiu
engolir (erro de rede fatal, exceção de programação, ...) propaga, marca o run
como "error" e notifica.

`status` tem portanto três valores: `success` (limpo), `degraded` (gravou o que
deu, engoliu erros) e `error` (perdeu a execução inteira). Um run `error` que
também engoliu erros parciais continua `error` — a falha fatal é a mais grave —
mas leva os parciais em `details` do mesmo jeito, que antes se perdiam.

No máximo uma notificação por execução — ver `_notify_result`. Sem isso, a API
da fonte fora do ar geraria uma dezena de pushes por execução, justamente no
dia em que ler o celular importa.
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
    """Decide se esta execução merece um push, e com qual severidade (ADR 0007).

    Três situações notificam, em ordem de gravidade:

    - **falhou**: a execução inteira foi perdida. Prioridade normal — a próxima
      execução agendada pode muito bem resolver sozinha.
    - **degradado**: gravou alguma coisa, mas engoliu erros pelo caminho.
    - **sem jogos**: nem erro houve, e ainda assim não veio nenhum jogo. É o
      modo de falha mais silencioso que existe aqui (a fonte responde 200 e o
      parser aceita, mas não acha nada) e o único que nenhuma exceção denuncia.

    Execução limpa não notifica — um push por coleta bem-sucedida, 4x por dia
    por fonte, treinaria qualquer um a ignorar os pushes.
    """
    job_label = f"{source.code}/{job_type}"
    run_label = f"run #{run_id}" if run_id is not None else "run não registrado"

    if status == "error":
        parts = [error_message or "erro sem mensagem"]
        if collected:
            parts.append(f"\nAntes de falhar:\n{collected.summary()}")
        parts.append(f"\n{run_label}")
        notify(f"{job_label} falhou", "\n".join(parts), priority=PRIORITY_ERROR)
        return

    if collected:
        plural = "erros" if collected.total > 1 else "erro"
        parts = [
            f"{collected.total} {plural} engolidos durante a execução.",
            "",
            collected.summary(),
            "",
            f"{_details_label(job_type, details)} · {run_label}",
        ]
        notify(f"{job_label} degradado", "\n".join(parts), priority=PRIORITY_WARNING)
        return

    if job_type == "games" and details.get("games_count") == 0:
        notify(
            f"{job_label} sem jogos",
            "A execução terminou sem erro algum e não gravou nenhum jogo.\n"
            "Provável mudança de contrato da fonte: ela respondeu, o parser "
            "aceitou, e não sobrou nada.\n\n"
            f"{run_label}",
            priority=PRIORITY_WARNING,
        )


def _details_label(job_type: str, details: dict) -> str:
    if job_type == "games":
        return f"{details.get('games_count', 0)} jogo(s) gravado(s)"
    return "catálogo sincronizado"


def _run(job_type: str, source: Source, fn) -> dict:
    started_at = dt.datetime.now(dt.timezone.utc)
    session = SessionLocal()
    status = "success"
    details: dict = {}
    error_message = None
    run_id = None
    collected = CollectedErrors()

    try:
        # Só `fn` fica sob o coletor: o `log.exception` abaixo é a falha total,
        # já reportada por `error_message`, e não deve entrar na agregação de
        # erros parciais.
        with collect_errors() as collected:
            details = fn(session)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - precisa registrar qualquer falha
        session.rollback()
        status = "error"
        error_message = f"{type(exc).__name__}: {exc}"
        log.exception("job %s (source=%s) falhou", job_type, source.code)
    finally:
        # O estado "degradado" (gravou, mas engoliu erros) precisa existir no
        # banco, não só no push: uma execução que só notificou não pode ser
        # contada como sucesso limpo por quem consultar `scrape_run` depois.
        # `error_message` continua reservado à falha fatal — os erros
        # engolidos vão para `details`, estruturados.
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

    # Fora do finally e depois do commit: a notificação nunca pode impedir o
    # `scrape_run` de ser gravado, e cita o id do run para quem for investigar.
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
        raise TypeError(f"fonte {source.code!r} não implementa sync_catalog (ADR 0004)")
    return _run("catalog", source, lambda session: sync_catalog(session))
