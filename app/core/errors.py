"""Coleta de erros parciais de uma execução, via `logging` (ADR 0007).

O problema: uma fonte que engole um erro para continuar (ex.: futnatv pula uma
data que a API recusou) termina com o job em `status="success"` — o core não
tem como saber que 16 de 20 requisições falharam. Notificar exige que esse erro
chegue até `app/core/jobs.py`.

A solução escolhida é não inventar canal novo: `collect_errors()` pluga um
`logging.Handler` durante a execução e agrega tudo que a aplicação logar em
nível ERROR ou acima. O `log.error(...)` que a fonte já escreve *é* o sinal —
nenhuma fonte precisa saber que este módulo existe, nem que Pushover existe
(a promessa do README: "adicionar uma fonte nova não toca app/core/" vale
também na direção contrária).

Dois cuidados que o handler precisa ter:

- **Escopo de logger.** Só escuta a árvore `app.*`; um `log.error` de urllib3
  ou do SQLAlchemy não é falha de coleta e não deve virar push.
- **Escopo de thread.** O APScheduler executa jobs num pool de threads, então
  duas coletas podem estar rodando ao mesmo tempo. O handler é global (está
  pendurado no logger `app`), mas só aceita registros da thread que abriu o
  coletor — senão os erros de um job vazariam para a notificação do outro.

A agregação é por *assinatura* (logger + template da mensagem + tipo da
exceção), não pela mensagem já formatada: as 16 falhas de
`"erro ao buscar %s %s: %s"` colapsam num grupo só com contagem 16, em vez de
16 linhas quase idênticas dentro do push.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

# Raiz da árvore de loggers da aplicação. Todo módulo usa
# `logging.getLogger(__name__)`, e `__name__` sempre começa com "app.".
APP_LOGGER_NAME = "app"

# Quantos grupos distintos cabem no corpo da notificação antes de resumir o
# resto numa linha só — o corpo do Pushover tem 1024 caracteres.
MAX_GROUPS_IN_SUMMARY = 5


@dataclass
class ErrorGroup:
    """Erros com a mesma assinatura, colapsados."""

    logger_name: str
    # O template do `log.error` ("erro ao buscar %s %s"), não a mensagem já
    # formatada: é ele que define o grupo, e é o único campo estável o
    # bastante para agregar por tipo de erro numa consulta posterior.
    template: str
    exc_type: str | None
    first_message: str
    count: int = 1

    @property
    def label(self) -> str:
        """Como o grupo se identifica numa mensagem.

        Sem `exc_info` (o caso comum: a fonte logou um erro que ela mesma já
        tratou), o melhor rótulo disponível é o módulo que reportou — sem o
        prefixo "app.", que é o mesmo para todos e só ocupa espaço.
        """
        return self.exc_type or self.logger_name.removeprefix(f"{APP_LOGGER_NAME}.")


@dataclass
class CollectedErrors:
    """Resultado de um `collect_errors()` — vazio quando nada falhou."""

    groups: dict[tuple, ErrorGroup] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.groups)

    @property
    def total(self) -> int:
        """Quantos registros de erro entraram, antes da agregação."""
        return sum(g.count for g in self.groups.values())

    def add(self, record: logging.LogRecord) -> None:
        exc_type = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None
        signature = (record.name, str(record.msg), exc_type)

        group = self.groups.get(signature)
        if group is not None:
            group.count += 1
            return

        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - args malformados não podem quebrar a coleta
            message = str(record.msg)

        self.groups[signature] = ErrorGroup(
            logger_name=record.name,
            template=str(record.msg),
            exc_type=exc_type,
            first_message=message,
        )

    def summary(self) -> str:
        """Corpo legível para a notificação: um bloco por grupo, com contagem."""
        lines: list[str] = []
        for group in list(self.groups.values())[:MAX_GROUPS_IN_SUMMARY]:
            header = group.label
            if group.count > 1:
                header = f"{header} ×{group.count}"
            lines.append(header)
            lines.append(f"  {group.first_message}")
            if group.count > 1:
                lines.append(f"  (+{group.count - 1} iguais)")

        remaining = len(self.groups) - MAX_GROUPS_IN_SUMMARY
        if remaining > 0:
            lines.append(f"(+{remaining} outro(s) tipo(s) de erro)")

        return "\n".join(lines)

    def as_records(self) -> list[dict]:
        """Os grupos em forma estruturada, para gravar em `scrape_run.details`.

        Diferente de `summary()`, que é texto renderizado para caber nos 1024
        caracteres do Pushover: aqui vão **todos** os grupos, em campos
        separados, para que uma consulta posterior possa agregar por tipo de
        erro em vez de fazer parsing de string.
        """
        return [
            {
                "label": group.label,
                "logger": group.logger_name,
                "template": group.template,
                "exc_type": group.exc_type,
                "count": group.count,
                "example": group.first_message,
            }
            for group in self.groups.values()
        ]


class _CollectingHandler(logging.Handler):
    def __init__(self, collected: CollectedErrors, thread_ident: int):
        super().__init__(level=logging.ERROR)
        self._collected = collected
        self._thread_ident = thread_ident
        self._lock_ = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self._thread_ident:
            return
        with self._lock_:
            self._collected.add(record)

    def handleError(self, record: logging.LogRecord) -> None:
        # Silencia: um erro dentro do coletor de erros não deve escrever no
        # stderr nem propagar para quem estava só logando.
        pass


@contextmanager
def collect_errors() -> Iterator[CollectedErrors]:
    """Agrega tudo que `app.*` logar em nível ERROR+ nesta thread, enquanto durar
    o bloco.

        with collect_errors() as collected:
            ...
        if collected:
            notify(...)
    """
    collected = CollectedErrors()
    handler = _CollectingHandler(collected, threading.get_ident())
    app_logger = logging.getLogger(APP_LOGGER_NAME)

    # Um handler só recebe registros que chegaram a ser criados, e `log.error()`
    # não cria nada se o nível efetivo do logger estiver acima de ERROR. Sem
    # esta garantia, subir o nível de log (`basicConfig(level=CRITICAL)`, um
    # `LOG_LEVEL` no ambiente) emudeceria o sistema de notificação inteiro, em
    # silêncio — o pior modo de falha possível para justamente este subsistema.
    # Abaixamos o nível só durante a execução e restauramos depois. O efeito
    # colateral é os erros passarem a aparecer também no stdout, que é desejado.
    nivel_original = app_logger.level
    if app_logger.getEffectiveLevel() > logging.ERROR:
        app_logger.setLevel(logging.ERROR)

    app_logger.addHandler(handler)
    try:
        yield collected
    finally:
        app_logger.removeHandler(handler)
        app_logger.setLevel(nivel_original)
