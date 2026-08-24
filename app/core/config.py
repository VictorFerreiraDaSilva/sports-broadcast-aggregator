"""Config genérica do agregador — nada aqui é específico de uma fonte.

Config por fonte fica em app/sources/<fonte>/config.py (ADR 0005).
"""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

DATABASE_URL = os.environ["DATABASE_URL"]

BRT = ZoneInfo("America/Sao_Paulo")

# Quantos dias à frente do dia atual capturar (0 = só hoje). O pedido é
# "hoje + 3 dias", então 4 datas no total por execução de `fetch_games`.
DAYS_AHEAD = 3

RUN_ON_STARTUP = os.environ.get("RUN_ON_STARTUP", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
