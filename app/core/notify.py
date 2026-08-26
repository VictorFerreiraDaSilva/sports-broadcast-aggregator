"""Envio de notificações de erro por Pushover — genérico, não conhece fonte
alguma (ADR 0005/0007).

Duas garantias que o resto do código depende:

1. **Nunca propaga.** Uma falha aqui (rede, credencial errada, rate limit da
   Pushover) vira `log.error` e retorna `False`. Notificação é observabilidade;
   derrubar uma coleta porque o push falhou seria trocar um problema pequeno
   por um grande.
2. **No-op sem credencial.** Sem `PUSHOVER_TOKEN`/`PUSHOVER_USER_KEY` o módulo
   fica inerte (um aviso só, no primeiro uso). É o que faz `pytest` e o dev
   local rodarem sem rede e sem configurar nada.
"""

from __future__ import annotations

import logging
import os
import threading

import requests

log = logging.getLogger(__name__)

PUSHOVER_API_URL = "https://api.pushover.net/1/messages.json"

PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "").strip()
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY", "").strip()

# Prefixo do título, para distinguir este app de outros que mandem pro mesmo
# celular. Configurável porque quem roda duas instâncias (prod/staging) precisa
# saber de qual veio o push.
PUSHOVER_APP_NAME = os.environ.get("PUSHOVER_APP_NAME", "fut").strip()

PUSHOVER_TIMEOUT_SECONDS = float(os.environ.get("PUSHOVER_TIMEOUT_SECONDS", "10"))

# Severidades usadas pelo projeto -> prioridade Pushover (ADR 0007).
# A prioridade 2 (emergência: repete até o usuário confirmar no app) fica
# deliberadamente sem uso — nada num agregador de calendário esportivo
# justifica acordar alguém às 3h da manhã.
PRIORITY_CRITICAL = 1  # fura as quiet hours do celular; não volta sozinho
PRIORITY_ERROR = 0  # som normal; a próxima execução agendada pode resolver
PRIORITY_WARNING = -1  # sem som; só aparece na lista de notificações

# Limites da API (https://pushover.net/api): título 250, corpo 1024.
_TITLE_LIMIT = 250
_MESSAGE_LIMIT = 1024

_warned_lock = threading.Lock()
_warned_unconfigured = False


def is_configured() -> bool:
    return bool(PUSHOVER_TOKEN and PUSHOVER_USER_KEY)


def _warn_unconfigured_once() -> None:
    global _warned_unconfigured
    with _warned_lock:
        if _warned_unconfigured:
            return
        _warned_unconfigured = True
    log.warning(
        "PUSHOVER_TOKEN/PUSHOVER_USER_KEY não configurados — "
        "notificações de erro desativadas (os erros continuam no log e em scrape_run)"
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def notify(title: str, message: str, priority: int = PRIORITY_ERROR) -> bool:
    """Manda um push. Devolve `True` se a Pushover aceitou.

    Não levanta exceção em hipótese alguma — ver o docstring do módulo.
    """
    if not is_configured():
        _warn_unconfigured_once()
        return False

    payload = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": _truncate(f"{PUSHOVER_APP_NAME} · {title}", _TITLE_LIMIT),
        "message": _truncate(message, _MESSAGE_LIMIT),
        "priority": priority,
    }

    try:
        resp = requests.post(PUSHOVER_API_URL, data=payload, timeout=PUSHOVER_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            # 4xx traz {"errors": [...]}; logar o corpo é o que diferencia
            # "token inválido" de "rate limit" quando alguém for investigar.
            log.error(
                "Pushover recusou a notificação: HTTP %s %s", resp.status_code, resp.text[:500]
            )
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - notificação nunca derruba quem chamou
        log.error("falha ao enviar notificação Pushover: %s", exc)
        return False
