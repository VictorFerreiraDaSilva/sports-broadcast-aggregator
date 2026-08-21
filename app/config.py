from __future__ import annotations

import os
from zoneinfo import ZoneInfo

BASE_URL = "https://futnatv.net"
SPORTS = ("futebol", "basquete", "volei", "nfl", "nhl")
BRT = ZoneInfo("America/Sao_Paulo")

# Quantos dias à frente do dia atual capturar (0 = só hoje). O pedido é
# "hoje + 3 dias", então 4 datas no total por execução.
DAYS_AHEAD = 3

DATABASE_URL = os.environ["DATABASE_URL"]

CONTACT_INFO = os.environ.get(
    "CONTACT_INFO", "fut-scraper/1.0 (uso pessoal; sem contato configurado)"
)
USER_AGENT = CONTACT_INFO

# Etiqueta técnica: ~1 req/s é folgado (ver docs/legal-e-etiqueta.md).
REQUEST_DELAY_SECONDS = float(os.environ.get("REQUEST_DELAY_SECONDS", "1.1"))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))

RUN_ON_STARTUP = os.environ.get("RUN_ON_STARTUP", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)
