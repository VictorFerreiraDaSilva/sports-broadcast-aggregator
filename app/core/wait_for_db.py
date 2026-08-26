"""Espera o Postgres aceitar conexão antes de qualquer outra coisa subir.

Roda no entrypoint *antes* de `alembic upgrade head` (ADR 0007). O motivo é
específico: com o banco fora do ar o alembic morre primeiro, o container morre
junto com ele e o `restart: unless-stopped` do compose o reinicia — nenhuma
linha de Python nossa chega a rodar, e o crash loop fica completamente mudo.

Em vez de morrer, este módulo insiste. O container fica de pé, notifica **uma
vez** que o banco está inacessível, continua tentando em silêncio e avisa de
novo quando conecta. Um banco fora por 10 minutos gera 2 notificações (caiu,
voltou) em vez das dezenas de pushes idênticos que um crash loop produziria.

    python -m app.core.wait_for_db
"""

from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import text

from app.core.notify import PRIORITY_CRITICAL, PRIORITY_WARNING, notify

log = logging.getLogger(__name__)

# Quanto tempo de falha contínua antes de incomodar o usuário. Um restart
# rotineiro do Postgres leva poucos segundos; notificar na primeira tentativa
# transformaria manutenção normal em push.
DB_WAIT_NOTIFY_AFTER_SECONDS = float(os.environ.get("DB_WAIT_NOTIFY_AFTER_SECONDS", "60"))

# Teto de espera total. 0 = espera indefinidamente, que é o default: é o que
# mantém o container vivo (e portanto silencioso) em vez de crash-loopando.
DB_WAIT_MAX_SECONDS = float(os.environ.get("DB_WAIT_MAX_SECONDS", "0"))

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0


def _check(engine) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def wait_for_db(engine=None) -> None:
    """Bloqueia até o banco responder. Só levanta se `DB_WAIT_MAX_SECONDS` for
    excedido (não é o default)."""
    if engine is None:
        from app.core.db import engine as default_engine

        engine = default_engine

    started = time.monotonic()
    backoff = _INITIAL_BACKOFF
    notified = False
    last_error = "erro desconhecido"
    attempt = 0

    while True:
        attempt += 1
        try:
            _check(engine)
        except Exception as exc:  # noqa: BLE001 - qualquer falha de conexão conta
            last_error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started

            if not notified and elapsed >= DB_WAIT_NOTIFY_AFTER_SECONDS:
                notify(
                    "banco inacessível",
                    "O container está de pé mas não consegue conectar no Postgres "
                    f"há {int(elapsed)}s ({attempt} tentativas).\n"
                    "Nenhuma coleta vai rodar até isso normalizar.\n\n"
                    f"{last_error[:500]}",
                    priority=PRIORITY_CRITICAL,
                )
                notified = True

            if DB_WAIT_MAX_SECONDS and elapsed >= DB_WAIT_MAX_SECONDS:
                raise RuntimeError(
                    f"banco inacessível após {int(elapsed)}s: {last_error}"
                ) from exc

            log.warning(
                "banco inacessível (tentativa %d, %ds): %s — nova tentativa em %.0fs",
                attempt, int(elapsed), last_error, backoff,
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
            continue

        elapsed = time.monotonic() - started
        if notified:
            notify(
                "banco recuperado",
                f"Conexão com o Postgres restabelecida após {int(elapsed)}s "
                f"e {attempt} tentativas. A inicialização segue normalmente.",
                priority=PRIORITY_WARNING,
            )
        if attempt > 1:
            log.info("banco disponível após %ds (%d tentativas)", int(elapsed), attempt)
        return


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    wait_for_db()


if __name__ == "__main__":
    main()
